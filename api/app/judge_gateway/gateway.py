"""判题网关：维护节点注册表 + Redis Stream 任务队列 + 结果回写

使用 Redis Stream 持久化任务，架构变化：
  - 任务入 Redis Stream（oj:judge:queue），节点主动消费
  - 节点完成判题后发布结果到 oj:judge:results Stream
  - 网关订阅结果 Stream 并写库
  - 支持 API 重启后任务不丢失、节点断连自动重投

节点生命周期：
  Connect(bidi 流) → Register(token 认证) → 心跳保活
  节点主动从 Redis Stream 拉取任务 → 判题 → 回传结果到结果 Stream
"""

import asyncio
import logging
import uuid

import grpc
from google.protobuf.empty_pb2 import Empty

from app.config import settings
from app.judge_gateway.gen.judge.v1 import judge_pb2, judge_pb2_grpc
from app.services.judge_queue import judge_queue

logger = logging.getLogger("judge-gateway")


class Node:
    """判题节点状态"""
    def __init__(self, node_id: str, name: str, capacity: int):
        self.node_id = node_id
        self.name = name
        self.capacity = capacity
        self.out_stream: asyncio.Queue | None = None  # 由 Connect 注入
        self.last_seen = 0.0
        self.running = 0


class JudgeGatewayServicer(judge_pb2_grpc.JudgeGatewayServicer):
    def __init__(self, result_sink=None):
        # result_sink: async fn(JudgeResult) -> None，由上层注入（写库/通知）
        self.result_sink = result_sink
        self.nodes: dict[str, Node] = {}
        self.pending: dict[str, asyncio.Future] = {}  # submission_id -> 等结果
        self._lock = asyncio.Lock()
        # 结果消费 task
        self._result_consumer_task: asyncio.Task | None = None

    # ---------- 供 FastAPI 侧调用 ----------

    async def start(self) -> None:
        """启动网关（初始化结果消费者）"""
        self._result_consumer_task = asyncio.create_task(
            self._result_consumer_loop()
        )

    async def stop(self) -> None:
        """停止网关"""
        if self._result_consumer_task:
            self._result_consumer_task.cancel()
            try:
                await self._result_consumer_task
            except asyncio.CancelledError:
                pass
            self._result_consumer_task = None

    async def submit(self, job: judge_pb2.SubmitJob, timeout: float = 120.0) -> judge_pb2.JudgeResult:
        """提交判题任务到 Redis Stream 并等待结果"""
        fut = asyncio.get_running_loop().create_future()
        self.pending[job.submission_id] = fut
        # 入 Redis Stream（序列化 proto 为 JSON）
        await judge_queue.enqueue_judge({
            "submission_id": job.submission_id,
            "language": job.language,
            "code": job.code.decode("utf-8", errors="replace"),
            "limits": {
                "time_limit_ms": job.limits.time_limit_ms,
                "memory_limit_mb": job.limits.memory_limit_mb,
                "output_limit_kb": job.limits.output_limit_kb,
                "process_limit": job.limits.process_limit,
            },
            "problem_id": job.problem_id,
            "data_version": job.data_version,
            "cases": [{"test_case_id": c.test_case_id, "score": c.score} for c in job.cases],
            "stop_on_failure": job.stop_on_failure,
        })
        try:
            return await asyncio.wait_for(fut, timeout)
        except asyncio.TimeoutError:
            self.pending.pop(job.submission_id, None)
            raise
        finally:
            self.pending.pop(job.submission_id, None)

    async def run_code(self, job: judge_pb2.RunCodeJob, timeout: float = 60.0) -> judge_pb2.RunCodeResult:
        """用户自测：单次运行代码，不比对不落库"""
        fut = asyncio.get_running_loop().create_future()
        self.pending[job.request_id] = fut
        await judge_queue.enqueue_run({
            "request_id": job.request_id,
            "language": job.language,
            "code": job.code.decode("utf-8", errors="replace"),
            "input": job.input.decode("utf-8", errors="replace"),
            "limits": {
                "time_limit_ms": job.limits.time_limit_ms,
                "memory_limit_mb": job.limits.memory_limit_mb,
                "output_limit_kb": job.limits.output_limit_kb,
                "process_limit": job.limits.process_limit,
            },
        })
        try:
            return await asyncio.wait_for(fut, timeout)
        except asyncio.TimeoutError:
            self.pending.pop(job.request_id, None)
            raise
        finally:
            self.pending.pop(job.request_id, None)

    async def node_count(self) -> int:
        return sum(1 for n in self.nodes.values() if n.out_stream is not None)

    async def snapshot(self) -> dict:
        """网关只读快照（/admin/judges 用）：节点列表 + 队列深度"""
        loop = asyncio.get_running_loop().time()
        nodes = [{
            "node_id": n.node_id,
            "name": n.name,
            "capacity": n.capacity,
            "running": n.running,
            "online": n.out_stream is not None,
            "last_seen_seconds_ago": round(loop - n.last_seen, 1) if n.last_seen else None,
        } for n in self.nodes.values()]
        queue_stats = await judge_queue.queue_stats()
        return {
            "nodes": nodes,
            "pending_count": len(self.pending),
            **queue_stats,
        }

    # ----------

    async def _resolve(self, result) -> None:
        """解析判题结果，设置 future 或回调 result_sink"""
        submission_id = result.get("submission_id")
        fut = self.pending.pop(submission_id, None)
        if fut and not fut.done():
            fut.set_result(result)
        elif fut is None and self.result_sink:
            # 主动推送模式的结果（重判等），交给上层落库
            asyncio.get_running_loop().create_task(self.result_sink(result))

    async def _resolve_run_code(self, rc) -> None:
        """解析自测结果"""
        request_id = rc.get("request_id")
        fut = self.pending.pop(request_id, None)
        if fut and not fut.done():
            fut.set_result(rc)

    async def _result_consumer_loop(self) -> None:
        """后台消费结果 Stream"""
        logger.info("结果消费者启动")
        while True:
            try:
                results = await judge_queue.consume_results("api-gateway", count=10)
                for msg_id, result in results:
                    if "submission_id" in result:
                        await self._resolve(result)
                    elif "request_id" in result:
                        await self._resolve_run_code(result)
                    await judge_queue.ack_result(msg_id)
            except asyncio.CancelledError:
                break
            except Exception:  # noqa: BLE001
                logger.exception("结果消费异常")
                await asyncio.sleep(1)

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
        node = Node(node_id, reg.name, reg.capacity or 1)
        node.out_stream = asyncio.Queue(64)
        node.last_seen = asyncio.get_running_loop().time()
        async with self._lock:
            self.nodes[node_id] = node
        logger.info("节点上线 %s (cap=%s)", node_id, reg.capacity)

        ack = judge_pb2.ServerMessage(ack=judge_pb2.RegisterAck(
            node_id=node_id, heartbeat_interval_seconds=10))
        await node.out_stream.put(ack)

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
                    # 结果入 Redis Stream，由后台消费者统一处理
                    await judge_queue.publish_result({
                        "submission_id": msg.result.submission_id,
                        "status": msg.result.status,
                        "score": msg.result.score,
                        "time_used_ms": msg.result.time_used_ms,
                        "memory_used_kb": msg.result.memory_used_kb,
                        "error_message": msg.result.error_message,
                        "cases": [
                            {
                                "test_case_id": c.test_case_id,
                                "status": c.status,
                                "time_used_ms": c.time_used_ms,
                                "memory_used_kb": c.memory_used_kb,
                                "score": c.score,
                                "output": c.output.decode("utf-8", errors="replace") if c.output else "",
                            }
                            for c in msg.result.cases
                        ],
                    })
                elif msg.HasField("run_code_result"):
                    node.running = max(0, node.running - 1)
                    await judge_queue.publish_result({
                        "request_id": msg.run_code_result.request_id,
                        "status": msg.run_code_result.status,
                        "output": msg.run_code_result.output.decode("utf-8", errors="replace"),
                        "error_message": msg.run_code_result.error_message,
                        "time_used_ms": msg.run_code_result.time_used_ms,
                        "memory_used_kb": msg.run_code_result.memory_used_kb,
                    })
        except Exception:  # noqa: BLE001 节点断开属正常生命周期
            pass

    async def FetchProblemData(self, request, context):
        """题目测试数据分块下发；x-node-token 元数据认证"""
        token = dict(context.invocation_metadata()).get("x-node-token")
        if token not in settings.judge_gateway_tokens:
            await context.abort(grpc.StatusCode.UNAUTHENTICATED, "token 无效")

        from app.services.problem_data import iter_problem_data
        async for path, content in iter_problem_data(request.problem_id, request.data_version):
            yield judge_pb2.FileChunk(path=path, content=content)
