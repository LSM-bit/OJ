"""AI 助手网关（信息：api/app/assistant_gateway/gateway.py；用途：维护 assistant 节点注册表、下发 ChatJob、把节点上行事件按 job_id 路由成异步流）

与判题网关同构，三点差异：
  1. judge 的 submit() 是 Future 等最终结果；这里是 stream_chat() 队列版——
     节点逐 token 回 ChatDelta，调用方（router 的 SSE 端点）逐事件消费；
  2. 工具执行留在 API 侧：router 收到 tool_use 事件后执行工具，再经
     send_tool_result() 回填节点续轮（节点零 DB/存储访问）；
  3. job 生命周期以 done/error 收尾，队列以 None 哨兵关闭。
"""

import asyncio
import logging
import uuid
from collections import deque

import grpc

from app.assistant_gateway.gen.assistant.v1 import assistant_pb2, assistant_pb2_grpc
from app.config import settings

logger = logging.getLogger("assistant-gateway")

_STREAM_QUEUE_SIZE = 512


class Node:
    def __init__(self, node_id: str, name: str, capacity: int):
        self.node_id = node_id
        self.name = name
        self.capacity = capacity
        self.out_stream: asyncio.Queue | None = None  # 待下发（ServerMessage），由 Connect 注入
        self.last_seen = 0.0
        self.running = 0


class AssistantGatewayServicer(assistant_pb2_grpc.AssistantGatewayServicer):
    def __init__(self):
        self.nodes: dict[str, Node] = {}
        self.pending: dict[str, asyncio.Queue] = {}  # job_id -> 事件队列（ChatDelta/ChatDone/ChatError/None）
        self.job_node: dict[str, str] = {}           # job_id -> 承接节点 id（回填 ToolResult / 计数归还）
        self.waiting_jobs: deque = deque()           # 无空闲节点时排队
        self._lock = asyncio.Lock()

    # ---------- 供 FastAPI 侧调用 ----------

    def has_capacity(self) -> bool:
        """是否至少有一个在线节点可立即承接（router 无节点时直接 503）"""
        return any(n.out_stream is not None for n in self.nodes.values())

    async def stream_chat(self, job, timeout: float = 120.0):
        """下发一轮对话并逐事件产出（ChatDelta → ChatDone/ChatError），结束后自动清理"""
        queue: asyncio.Queue = asyncio.Queue(_STREAM_QUEUE_SIZE)
        self.pending[job.job_id] = queue
        await self._dispatch(job)
        try:
            while True:
                evt = await asyncio.wait_for(queue.get(), timeout)
                if evt is None:
                    return
                yield evt
        finally:
            self.pending.pop(job.job_id, None)
            self._release_job(job.job_id)
            self._try_redistribute()

    async def send_tool_result(self, job_id: str, tool_use_id: str,
                               content_json: str, is_error: bool = False) -> None:
        """把 API 侧执行完的工具结果回填给承接节点（节点等待后续下一轮）"""
        node = self._node_of(job_id)
        if node is None or node.out_stream is None:
            raise RuntimeError("助手节点已断开，无法回填工具结果")
        await node.out_stream.put(assistant_pb2.ServerMessage(
            tool_result=assistant_pb2.ToolResult(
                job_id=job_id, tool_use_id=tool_use_id,
                content_json=content_json, is_error=is_error)))

    async def cancel_chat(self, job_id: str) -> None:
        """客户端提前断开时通知节点停止（尽力而为，节点侧收到后中止在飞请求）"""
        node = self._node_of(job_id)
        if node is not None and node.out_stream is not None:
            await node.out_stream.put(assistant_pb2.ServerMessage(
                cancel=assistant_pb2.CancelChat(job_id=job_id)))

    def snapshot(self) -> dict:
        """网关只读快照（/health 与 ADMIN 监控用）"""
        loop = asyncio.get_running_loop().time()
        nodes = [{
            "node_id": n.node_id, "name": n.name, "capacity": n.capacity,
            "running": n.running, "online": n.out_stream is not None,
            "last_seen_seconds_ago": round(loop - n.last_seen, 1) if n.last_seen else None,
        } for n in self.nodes.values()]
        return {"nodes": nodes, "queue_length": len(self.waiting_jobs),
                "active_jobs": len(self.job_node)}

    # ---------- 内部 ----------

    def _node_of(self, job_id: str) -> Node | None:
        node_id = self.job_node.get(job_id)
        return self.nodes.get(node_id) if node_id else None

    def _release_job(self, job_id: str) -> None:
        """归还节点并发计数（幂等：仅首次 pop 成功时递减）"""
        node_id = self.job_node.pop(job_id, None)
        if node_id:
            node = self.nodes.get(node_id)
            if node:
                node.running = max(0, node.running - 1)

    async def _dispatch(self, job) -> None:
        for node in self.nodes.values():
            if node.out_stream is not None and node.running < node.capacity:
                node.running += 1
                self.job_node[job.job_id] = node.node_id
                await node.out_stream.put(assistant_pb2.ServerMessage(job=job))
                return
        self.waiting_jobs.append(job)
        asyncio.get_running_loop().call_soon(self._try_redistribute)

    def _try_redistribute(self) -> None:
        while self.waiting_jobs:
            job = self.waiting_jobs[0]
            placed = False
            for node in self.nodes.values():
                if node.out_stream is not None and node.running < node.capacity:
                    node.running += 1
                    self.job_node[job.job_id] = node.node_id
                    node.out_stream.put_nowait(assistant_pb2.ServerMessage(job=job))
                    placed = True
                    break
            if not placed:
                return
            self.waiting_jobs.popleft()

    def _route(self, job_id: str, evt) -> None:
        queue = self.pending.get(job_id)
        if queue is not None:
            queue.put_nowait(evt)

    async def _read_incoming(self, request_iterator) -> None:
        """持续读取节点上行：delta 透传队列；done/error 收尾并归还容量"""
        try:
            async for msg in request_iterator:
                if msg.HasField("heartbeat"):
                    # last_seen 由 Connect 主循环统一刷新
                    pass
                elif msg.HasField("delta"):
                    self._route(msg.delta.job_id, msg.delta)
                elif msg.HasField("done"):
                    self._route(msg.done.job_id, msg.done)
                    self._route(msg.done.job_id, None)
                    self._release_job(msg.done.job_id)
                    self._try_redistribute()
                elif msg.HasField("error"):
                    self._route(msg.error.job_id, msg.error)
                    self._route(msg.error.job_id, None)
                    self._release_job(msg.error.job_id)
                    self._try_redistribute()
        except Exception:  # noqa: BLE001 节点断开属正常生命周期
            pass

    # ---------- gRPC 服务实现 ----------

    async def Connect(self, request_iterator, context):
        first = None
        async for msg in request_iterator:
            first = msg
            break
        if first is None or not first.HasField("register"):
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, "必须先发送 Register")
        reg = first.register
        if reg.token not in settings.assistant_node_tokens:
            await context.abort(grpc.StatusCode.UNAUTHENTICATED, "token 无效")

        node_id = reg.node_id or f"{reg.name or 'assistant'}-{uuid.uuid4().hex[:8]}"
        node = Node(node_id, reg.name, reg.capacity or 1)
        node.out_stream = asyncio.Queue(64)
        node.last_seen = asyncio.get_running_loop().time()
        async with self._lock:
            self.nodes[node_id] = node
        logger.info("助手节点上线 %s (cap=%s)", node_id, reg.capacity)

        await node.out_stream.put(assistant_pb2.ServerMessage(
            ack=assistant_pb2.RegisterAck(node_id=node_id, heartbeat_interval_seconds=10)))
        self._try_redistribute()

        async def _out_gen():
            while True:
                msg = await node.out_stream.get()
                node.out_stream.task_done()
                yield msg

        reader_task = asyncio.create_task(self._read_incoming(request_iterator))
        try:
            async for msg in _out_gen():
                node.last_seen = asyncio.get_running_loop().time()
                yield msg
        finally:
            reader_task.cancel()
            async with self._lock:
                self.nodes.pop(node_id, None)
            # 该节点在飞 job 全部以错误收尾，唤醒等待中的 stream_chat
            for job_id, owner in list(self.job_node.items()):
                if owner == node_id:
                    self._route(job_id, assistant_pb2.ChatError(
                        job_id=job_id, message="助手节点连接中断，请重试"))
                    self._route(job_id, None)
                    self._release_job(job_id)
            logger.info("助手节点离线 %s", node_id)
