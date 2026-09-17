"""OJ 判题节点：连接 API 网关，从 Redis Stream 拉取任务并在 nsjail 沙箱内判题

用法: python -m judge_node.daemon --config node.toml

架构变化：
  - 节点仍然通过 gRPC 连接网关（注册/心跳/结果回传）
  - 判题/自测任务从 Redis Stream 主动拉取（代替网关推送）
  - 支持多节点并发消费，任务自动负载均衡
"""

import argparse
import asyncio
import contextlib
import json
import logging
import os
import platform
import sys
from pathlib import Path

import grpc
import redis.asyncio as aioredis

sys.path.insert(0, str(Path(__file__).resolve().parent))

from gen.judge.v1 import judge_pb2, judge_pb2_grpc  # noqa: E402
from executor import JudgeWorker, JudgeCase, ResourceLimits  # noqa: E402
from datacache import ProblemDataCache  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("judge-node")

STATUS_HIGHEST_SEVERITY = (
    "compile_error", "system_error", "time_limit_exceeded",
    "memory_limit_exceeded", "output_limit_exceeded", "runtime_error", "wrong_answer",
)

# 重连退避：失败后按 1s 起步指数增长，封顶 30s（连接成功后清零）
RECONNECT_BASE_SECONDS = 1.0
RECONNECT_MAX_SECONDS = 30.0

# Redis Stream key 常量（与 api/app/services/judge_queue.py 保持一致）
STREAM_JUDGE_QUEUE = "oj:judge:queue"
STREAM_JUDGE_RUN = "oj:judge:run"
STREAM_JUDGE_RESULTS = "oj:judge:results"
GROUP_JUDGE = "judge-nodes"


def aggregate_status(statuses: list[str]) -> str:
    """整题判定 = 最严重的测试点状态；全 AC 才 accepted"""
    if not statuses:
        return "system_error"
    for s in STATUS_HIGHEST_SEVERITY:
        if s in statuses:
            return s
    return "accepted" if all(x == "accepted" for x in statuses) else "system_error"


class NodeDaemon:
    def __init__(self, cfg):
        self.cfg = cfg
        self.worker = JudgeWorker(workspace_root=cfg.paths.workspace)
        self.cache = ProblemDataCache(Path(cfg.paths.data_cache))
        self.semaphore = asyncio.Semaphore(cfg.node.capacity)
        self.running_tasks = 0
        self.backoff = RECONNECT_BASE_SECONDS
        self.node_id = cfg.node.id or f"{cfg.node.name or 'node'}-{os.urandom(4).hex()}"
        self.redis: aioredis.Redis | None = None
        self.grpc_stub: judge_pb2_grpc.JudgeGatewayStub | None = None

    async def run(self):
        """主循环：连接 → 服务 → 断开后指数退避重连"""
        redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
        self.redis = aioredis.from_url(redis_url, decode_responses=True, max_connections=5)
        # 确保 consumer group 存在
        for stream, group in [
            (STREAM_JUDGE_QUEUE, GROUP_JUDGE),
            (STREAM_JUDGE_RUN, GROUP_JUDGE),
        ]:
            try:
                await self.redis.xgroup_create(stream, group, id="0", mkstream=True)
            except Exception:  # noqa: BLE001 BUSYGROUP
                pass
        log.info("Redis 连接建立: %s", redis_url)

        try:
            while True:
                try:
                    await self._run_once()
                except grpc.aio.AioRpcError as e:
                    log.error("连接断开: %s，%.0fs 后重连",
                              e.code(), min(self.backoff, RECONNECT_MAX_SECONDS))
                except Exception:  # noqa: BLE001
                    log.exception("节点运行异常，%.0fs 后重连",
                                  min(self.backoff, RECONNECT_MAX_SECONDS))
                await asyncio.sleep(min(self.backoff, RECONNECT_MAX_SECONDS))
                self.backoff = min(self.backoff * 2, RECONNECT_MAX_SECONDS)
        finally:
            if self.redis:
                await self.redis.close()

    async def _run_once(self):
        channel = grpc.aio.insecure_channel(self.cfg.server.address)
        self.grpc_stub = judge_pb2_grpc.JudgeGatewayStub(channel)
        self.outbox: asyncio.Queue = asyncio.Queue(64)

        async def request_gen():
            yield judge_pb2.NodeMessage(register=judge_pb2.Register(
                token=self.cfg.server.token,
                node_id=self.node_id,
                name=self.cfg.node.name or platform.node(),
                capacity=self.cfg.node.capacity,
                version="0.1.0",
            ))
            while True:
                msg = await self.outbox.get()
                if msg is None:
                    return
                yield msg

        heartbeat_task = asyncio.create_task(self._heartbeat_loop())
        poll_task = asyncio.create_task(self._poll_jobs())
        log.info("连接网关 %s ...", self.cfg.server.address)
        try:
            async for server_msg in self.grpc_stub.Connect(request_gen()):
                if server_msg.HasField("ack"):
                    log.info("注册成功 node_id=%s 心跳=%ss",
                             server_msg.ack.node_id, server_msg.ack.heartbeat_interval_seconds)
                    self.backoff = RECONNECT_BASE_SECONDS
        finally:
            for task in (poll_task, heartbeat_task):
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

    async def _heartbeat_loop(self):
        while True:
            await asyncio.sleep(10)
            await self.outbox.put(judge_pb2.NodeMessage(heartbeat=judge_pb2.Heartbeat(
                running_tasks=self.running_tasks)))

    # ---------- Redis Stream 任务拉取 ----------

    async def _poll_jobs(self):
        """从 Redis Stream 轮询判题/自测任务"""
        log.info("开始从 Redis Stream 拉取任务")
        while True:
            try:
                # 先尝试投递该 consumer 的 pending 消息（断连重连场景）
                judge_jobs = await self._claim_jobs(STREAM_JUDGE_QUEUE, timeout_ms=2000)
                if judge_jobs:
                    msg_id, job = judge_jobs[0]
                    await self._execute_redis_job(msg_id, job)
                    continue

                run_jobs = await self._claim_jobs(STREAM_JUDGE_RUN, timeout_ms=1000)
                if run_jobs:
                    msg_id, job = run_jobs[0]
                    await self._execute_redis_run_code(msg_id, job)
                    continue

                await asyncio.sleep(0.5)
            except asyncio.CancelledError:
                break
            except Exception:  # noqa: BLE001
                log.exception("任务拉取异常")
                await asyncio.sleep(1)

    async def _claim_jobs(self, stream: str, timeout_ms: int = 2000, count: int = 1):
        """从 Redis Stream 拉取任务，先检查 pending 再拉新消息"""
        # 检查 pending（超时 30s 未 ACK 的）
        try:
            pending = await self.redis.xpending_range(
                stream, GROUP_JUDGE, min="-", max="+", count=count, consumername=self.node_id
            )
            if pending:
                old_ids = [
                    p["message_id"] for p in pending
                    if p["time_since_delivered"] > 30000
                ]
                if old_ids:
                    claimed = await self.redis.xclaim(
                        stream, GROUP_JUDGE, self.node_id, min_idle_time=0, message_ids=old_ids
                    )
                    result = []
                    for msg_id, fields in claimed:
                        if fields:
                            job = json.loads(fields.get("data", "{}"))
                            result.append((msg_id, job))
                    if result:
                        return result
        except Exception:  # noqa: BLE001
            pass

        # 拉取新消息
        resp = await self.redis.xreadgroup(
            GROUP_JUDGE, self.node_id, {stream: ">"},
            count=count, block=timeout_ms,
        )
        if not resp:
            return []
        result = []
        for _stream, messages in resp:
            for msg_id, fields in messages:
                job = json.loads(fields.get("data", "{}"))
                result.append((msg_id, job))
        return result

    async def _ack(self, stream: str, msg_id: str):
        """ACK 任务完成"""
        await self.redis.xack(stream, GROUP_JUDGE, msg_id)

    async def _publish_result(self, result: dict):
        """发布结果到结果 Stream"""
        await self.redis.xadd(
            STREAM_JUDGE_RESULTS,
            {"data": json.dumps(result, ensure_ascii=False)},
        )

    # ---------- 判题 ----------

    async def _execute_redis_job(self, msg_id: str, job: dict):
        """执行从 Redis 拉取的判题任务"""
        async with self.semaphore:
            self.running_tasks += 1
            try:
                result = await self._judge_inner(job)
                await self._ack(STREAM_JUDGE_QUEUE, msg_id)
            except Exception as exc:  # noqa: BLE001
                log.exception("作业异常 submission=%s", job.get("submission_id"))
                result = {"submission_id": job.get("submission_id"), "status": "system_error",
                          "error_message": f"node error: {exc}"[:2000], "cases": []}
                await self._ack(STREAM_JUDGE_QUEUE, msg_id)
            finally:
                self.running_tasks -= 1
            # 通过 gRPC 回传结果 + 发布到 Redis 结果 Stream
            await self.outbox.put(_result_message(result))
            await self._publish_result(result)
            log.info("判题完成 %s → %s", job.get("submission_id"), result["status"])

    async def _judge_inner(self, job: dict) -> dict:
        submission_id = job["submission_id"]
        data_dir = await self._ensure_data(job)
        limits = ResourceLimits(
            time_limit_ms=job["limits"].get("time_limit_ms", 2000),
            memory_limit_mb=job["limits"].get("memory_limit_mb", 256),
            output_limit_kb=job["limits"].get("output_limit_kb", 1024),
            process_limit=job["limits"].get("process_limit", 32),
        )
        cases = []
        for tc in job.get("cases", []):
            stdin = (data_dir / "cases" / f"{tc['test_case_id']}.in").read_bytes()
            expected = (data_dir / "cases" / f"{tc['test_case_id']}.out").read_bytes()
            cases.append(JudgeCase(language=job["language"], source=job["code"].encode(),
                                   stdin=stdin, expected=expected, limits=limits,
                                   case_id=tc["test_case_id"], score=tc["score"]))
        results = await asyncio.to_thread(self.worker.execute_cases, cases,
                                          stop_on_failure=job.get("stop_on_failure", True))

        case_results = []
        total_score = 0
        for case, res in zip(cases, results):
            if res.status == "accepted":
                total_score += case.score
            case_results.append({
                "test_case_id": case.case_id, "status": res.status,
                "time_used_ms": res.time_used_ms, "memory_used_kb": res.memory_used_kb,
                "score": case.score if res.status == "accepted" else 0,
                "output": res.stdout if res.status == "wrong_answer" else b"",
            })
        status = aggregate_status([r.status for r in results])
        error_message = ""
        if status in ("compile_error", "runtime_error"):
            error_message = results[0].stderr.decode("utf-8", errors="replace")[:8000]
        max_time = max((r.time_used_ms for r in results), default=0)
        max_mem = max((r.memory_used_kb for r in results), default=0)
        return {"submission_id": submission_id, "status": status, "score": total_score,
                "time_used_ms": max_time, "memory_used_kb": max_mem,
                "error_message": error_message, "cases": case_results}

    async def _ensure_data(self, job: dict) -> Path:
        """节点本地缓存命中直接用；否则从网关 gRPC 流式拉取"""
        problem_id = job["problem_id"]
        data_version = job["data_version"]
        if self.cache.has(problem_id, data_version):
            return self.cache.dir_for(problem_id, data_version)

        # 通过 gRPC FetchProblemData 拉取
        metadata = (("x-node-token", self.cfg.server.token),)
        call = self.grpc_stub.FetchProblemData(
            judge_pb2.ProblemDataRequest(problem_id=problem_id, data_version=data_version),
            metadata=metadata)
        return await self.cache.sync(problem_id, data_version, call)

    # ---------- 用户自测 ----------

    async def _execute_redis_run_code(self, msg_id: str, job: dict):
        """执行从 Redis 拉取自测任务"""
        async with self.semaphore:
            self.running_tasks += 1
            try:
                limits = ResourceLimits(
                    time_limit_ms=job["limits"].get("time_limit_ms", 5000),
                    memory_limit_mb=job["limits"].get("memory_limit_mb", 256),
                    output_limit_kb=job["limits"].get("output_limit_kb", 1024))
                result = await asyncio.to_thread(
                    self.worker.run_code, job["language"], job["code"].encode(),
                    job.get("input", "").encode(), limits)
                await self._ack(STREAM_JUDGE_RUN, msg_id)
            except Exception as exc:  # noqa: BLE001
                log.exception("自测异常 request=%s", job.get("request_id"))
                result = {"status": "system_error", "output": b"",
                          "error_message": f"node error: {exc}"[:2000]}
                await self._ack(STREAM_JUDGE_RUN, msg_id)
            finally:
                self.running_tasks -= 1

        # 通过 gRPC 回传 + 发布到 Redis 结果 Stream
        run_result = judge_pb2.RunCodeResult(
            request_id=job.get("request_id"), status=result["status"],
            output=result["output"] if isinstance(result["output"], bytes) else result["output"].encode(),
            error_message=result.get("error_message", ""),
            time_used_ms=result.get("time_used_ms", 0),
            memory_used_kb=result.get("memory_used_kb", 0))
        await self.outbox.put(judge_pb2.NodeMessage(run_code_result=run_result))
        await self._publish_result({
            "request_id": job.get("request_id"),
            "status": result["status"],
            "output": result["output"].decode("utf-8", errors="replace") if isinstance(result["output"], bytes) else result.get("output", ""),
            "error_message": result.get("error_message", ""),
            "time_used_ms": result.get("time_used_ms", 0),
            "memory_used_kb": result.get("memory_used_kb", 0),
        })


def _result_message(result: dict) -> judge_pb2.NodeMessage:
    return judge_pb2.NodeMessage(result=judge_pb2.JudgeResult(
        submission_id=result["submission_id"], status=result["status"],
        score=result.get("score", 0), time_used_ms=result.get("time_used_ms", 0),
        memory_used_kb=result.get("memory_used_kb", 0),
        error_message=result.get("error_message", ""),
        cases=[judge_pb2.CaseResult(**c) for c in result.get("cases", [])]))


def main():
    parser = argparse.ArgumentParser(description="OJ 判题节点")
    parser.add_argument("--config", default="node.toml")
    args = parser.parse_args()

    import tomllib
    with open(args.config, "rb") as f:
        cfg = tomllib.load(f)

    # 环境变量覆盖（容器部署用）
    cfg["server"]["address"] = os.environ.get("SERVER_ADDRESS", cfg["server"]["address"])
    cfg["server"]["token"] = os.environ.get("SERVER_TOKEN", cfg["server"]["token"])

    from types import SimpleNamespace
    c = SimpleNamespace(**{
        "server": SimpleNamespace(**cfg["server"]),
        "node": SimpleNamespace(**cfg["node"]),
        "paths": SimpleNamespace(**cfg["paths"]),
    })
    asyncio.run(NodeDaemon(c).run())


if __name__ == "__main__":
    main()
