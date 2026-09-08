"""判题网关：维护节点注册表 + 任务下发 + 结果回写

节点生命周期：
  Connect(bidi 流) → Register(token 认证) → 网关持续下发 SubmitJob
  节点回传 JudgeResult → 回调 result_sink（写 DB / 推 WebSocket）
  心跳超时的节点被摘除，其 in-flight 任务由任务池重新调度
"""

import asyncio
import logging
import uuid
from collections import defaultdict, deque

import grpc
from google.protobuf.empty_pb2 import Empty

from app.config import settings
from app.judge_gateway.gen.judge.v1 import judge_pb2, judge_pb2_grpc

logger = logging.getLogger("judge-gateway")


class Node:
    def __init__(self, node_id: str, name: str, capacity: int, queue: asyncio.Queue):
        self.node_id = node_id
        self.name = name
        self.capacity = capacity
        self.queue = queue          # 待下发任务（ServerMessage）
        self.out_stream: asyncio.Queue | None = None  # 由 Connect 注入
        self.last_seen = 0.0
        self.running = 0


class JudgeGatewayServicer(judge_pb2_grpc.JudgeGatewayServicer):
    def __init__(self, result_sink=None):
        # result_sink: async fn(JudgeResult) -> None，由上层注入（写库/通知）
        self.result_sink = result_sink
        self.nodes: dict[str, Node] = {}
        self.pending: dict[str, asyncio.Future] = {}  # submission_id -> 等结果
        self.waiting_jobs: deque = deque()            # 无空闲节点时排队
        self._lock = asyncio.Lock()

    # ---------- 供 FastAPI 侧调用 ----------

    async def submit(self, job: judge_pb2.SubmitJob, timeout: float = 120.0) -> judge_pb2.JudgeResult:
        """提交判题任务并等待结果（FastAPI 路由调用）"""
        fut = asyncio.get_running_loop().create_future()
        self.pending[job.submission_id] = fut
        await self._dispatch(job)
        try:
            return await asyncio.wait_for(fut, timeout)
        finally:
            self.pending.pop(job.submission_id, None)

    async def run_code(self, job: judge_pb2.RunCodeJob, timeout: float = 60.0) -> judge_pb2.RunCodeResult:
        """用户自测：单次运行代码，不比对不落库"""
        fut = asyncio.get_running_loop().create_future()
        self.pending[job.request_id] = fut  # pending 共用：request_id 与 submission_id 空间隔离
        await self._dispatch_run_code(job)
        try:
            return await asyncio.wait_for(fut, timeout)
        finally:
            self.pending.pop(job.request_id, None)

    async def node_count(self) -> int:
        return sum(1 for n in self.nodes.values() if n.out_stream is not None)

    def snapshot(self) -> dict:
        """网关只读快照（/admin/judges 用）：节点列表 + 队列深度，不产生 gRPC 往返"""
        loop = asyncio.get_running_loop().time()
        nodes = [{
            "node_id": n.node_id,
            "name": n.name,
            "capacity": n.capacity,
            "running": n.running,
            "online": n.out_stream is not None,
            "last_seen_seconds_ago": round(loop - n.last_seen, 1) if n.last_seen else None,
        } for n in self.nodes.values()]
        return {"nodes": nodes, "queue_length": len(self.waiting_jobs),
                "pending_count": len(self.pending)}

    # ---------- 内部 ----------

    async def _dispatch(self, job) -> None:
        # 找一个有空余容量的在线节点
        for node in self.nodes.values():
            if node.out_stream is not None and node.running < node.capacity:
                node.running += 1
                await node.out_stream.put(judge_pb2.ServerMessage(job=job))
                return
        self.waiting_jobs.append(job)
        # 有排队的任务时顺便唤醒一轮调度
        asyncio.get_running_loop().call_soon(self._try_redistribute)

    async def _dispatch_run_code(self, job) -> None:
        """自测任务下发；无可用节点直接报错（不排队，自测要求低延迟）"""
        for node in self.nodes.values():
            if node.out_stream is not None and node.running < node.capacity:
                node.running += 1
                await node.out_stream.put(judge_pb2.ServerMessage(run_code=job))
                return
        raise RuntimeError("没有可用的判题节点")

    def _try_redistribute(self) -> None:
        while self.waiting_jobs:
            job = self.waiting_jobs[0]
            placed = False
            for node in self.nodes.values():
                if node.out_stream is not None and node.running < node.capacity:
                    node.running += 1
                    node.out_stream.put_nowait(judge_pb2.ServerMessage(job=job))
                    placed = True
                    break
            if not placed:
                return
            self.waiting_jobs.popleft()

    def _resolve(self, result) -> None:
        fut = self.pending.pop(result.submission_id, None)
        if fut and not fut.done():
            fut.set_result(result)
        elif fut is None and self.result_sink:
            # 主动推送模式的结果（重判等），交给上层落库
            asyncio.get_running_loop().create_task(self.result_sink(result))

    # ---------- gRPC 服务实现 ----------

    async def Connect(self, request_iterator, context):
        first = None
        async for msg in request_iterator:
            first = msg
            break
        if first is None or not first.HasField("register"):
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, "必须先发送 Register")
        reg = first.register
        if reg.token not in settings.judge_gateway_tokens:
            await context.abort(grpc.StatusCode.UNAUTHENTICATED, "token 无效")

        node_id = reg.node_id or f"{reg.name or 'node'}-{uuid.uuid4().hex[:8]}"
        node = Node(node_id, reg.name, reg.capacity or 1, asyncio.Queue(64))
        node.out_stream = asyncio.Queue(64)
        node.last_seen = asyncio.get_running_loop().time()
        async with self._lock:
            self.nodes[node_id] = node
        logger.info("节点上线 %s (cap=%s)", node_id, reg.capacity)

        ack = judge_pb2.ServerMessage(ack=judge_pb2.RegisterAck(
            node_id=node_id, heartbeat_interval_seconds=10))
        await node.out_stream.put(ack)
        self._try_redistribute()

        async def _out_gen():
            while True:
                msg = await node.out_stream.get()
                node.out_stream.task_done()
                yield msg

        out_gen = _out_gen()
        reader_task = asyncio.create_task(self._read_incoming(node, request_iterator))
        try:
            async for msg in out_gen:
                yield msg
        finally:
            reader_task.cancel()
            async with self._lock:
                self.nodes.pop(node_id, None)
            logger.info("节点离线 %s", node_id)

    async def _read_incoming(self, node, request_iterator) -> None:
        """持续读取节点上行消息（心跳/结果）"""
        try:
            async for msg in request_iterator:
                node.last_seen = asyncio.get_running_loop().time()
                if msg.HasField("heartbeat"):
                    pass  # 已更新 last_seen；CPU/内存指标留给监控接口
                elif msg.HasField("result"):
                    node.running = max(0, node.running - 1)
                    self._resolve(msg.result)
                    self._try_redistribute()
                elif msg.HasField("run_code_result"):
                    node.running = max(0, node.running - 1)
                    self._resolve_run_code(msg.run_code_result)
                    self._try_redistribute()
        except Exception:  # noqa: BLE001 节点断开属正常生命周期
            pass

    def _resolve_run_code(self, rc) -> None:
        fut = self.pending.pop(rc.request_id, None)
        if fut and not fut.done():
            fut.set_result(rc)

    async def FetchProblemData(self, request, context):
        """题目测试数据分块下发；x-node-token 元数据认证"""
        token = dict(context.invocation_metadata()).get("x-node-token")
        if token not in settings.judge_gateway_tokens:
            await context.abort(grpc.StatusCode.UNAUTHENTICATED, "token 无效")

        from app.services.problem_data import iter_problem_data
        async for path, content in iter_problem_data(request.problem_id, request.data_version):
            yield judge_pb2.FileChunk(path=path, content=content)
