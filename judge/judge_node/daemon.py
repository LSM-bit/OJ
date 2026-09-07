"""OJ 判题节点：连接 API 网关，接收 SubmitJob，在 nsjail 沙箱内判题

用法: python -m judge_node.daemon --config node.toml
"""

import argparse
import asyncio
import base64
import json
import logging
import os
import platform
import sys
from pathlib import Path

import grpc

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

    async def run(self):
        channel = grpc.aio.insecure_channel(self.cfg.server.address)
        stub = judge_pb2_grpc.JudgeGatewayStub(channel)
        self.outbox: asyncio.Queue = asyncio.Queue(64)

        async def request_gen():
            yield judge_pb2.NodeMessage(register=judge_pb2.Register(
                token=self.cfg.server.token,
                node_id=self.cfg.node.id,
                name=self.cfg.node.name or platform.node(),
                capacity=self.cfg.node.capacity,
                version="0.1.0",
            ))
            while True:
                msg = await self.outbox.get()
                if msg is None:
                    return
                yield msg

        heartbeat_task = asyncio.create_task(self._heartbeat_loop(stub))
        log.info("连接网关 %s ...", self.cfg.server.address)
        try:
            async for server_msg in stub.Connect(request_gen()):
                if server_msg.HasField("ack"):
                    log.info("注册成功 node_id=%s 心跳=%ss",
                             server_msg.ack.node_id, server_msg.ack.heartbeat_interval_seconds)
                elif server_msg.HasField("job"):
                    asyncio.create_task(self._execute_job(stub, server_msg.job))
                elif server_msg.HasField("run_code"):
                    asyncio.create_task(self._execute_run_code(server_msg.run_code))
                elif server_msg.HasField("cancel"):
                    pass  # 一期暂不支持取消
        except grpc.aio.AioRpcError as e:
            log.error("连接断开: %s，5s 后重连", e.code())
        finally:
            heartbeat_task.cancel()

    async def _heartbeat_loop(self, stub):
        while True:
            await asyncio.sleep(10)
            await self.outbox.put(judge_pb2.NodeMessage(heartbeat=judge_pb2.Heartbeat(
                running_tasks=self.running_tasks)))

    # ---------- 判题 ----------

    async def _execute_job(self, stub, job: judge_pb2.SubmitJob):
        async with self.semaphore:
            self.running_tasks += 1
            try:
                result = await self._judge_inner(stub, job)
            except Exception as exc:  # noqa: BLE001
                log.exception("作业异常 submission=%s", job.submission_id)
                result = {"submission_id": job.submission_id, "status": "system_error",
                          "error_message": f"node error: {exc}"[:2000], "cases": []}
            finally:
                self.running_tasks -= 1
            await self.outbox.put(_result_message(result))
            log.info("判题完成 %s → %s", job.submission_id, result["status"])

    async def _judge_inner(self, stub, job: judge_pb2.SubmitJob) -> dict:
        data_dir = await self._ensure_data(stub, job)
        limits = ResourceLimits(
            time_limit_ms=job.limits.time_limit_ms or 2000,
            memory_limit_mb=job.limits.memory_limit_mb or 256,
            output_limit_kb=job.limits.output_limit_kb or 1024,
            process_limit=job.limits.process_limit or 32,
        )
        cases = []
        for tc in job.cases:
            stdin = (data_dir / "cases" / f"{tc.test_case_id}.in").read_bytes()
            expected = (data_dir / "cases" / f"{tc.test_case_id}.out").read_bytes()
            cases.append(JudgeCase(language=job.language, source=job.code,
                                   stdin=stdin, expected=expected, limits=limits,
                                   case_id=tc.test_case_id, score=tc.score))
        # 判题为阻塞进程等待，移出事件循环线程
        results = await asyncio.to_thread(self.worker.execute_cases, cases,
                                          stop_on_failure=job.stop_on_failure)

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
        if status == "compile_error":
            error_message = results[0].stderr.decode("utf-8", errors="replace")[:8000]
        max_time = max((r.time_used_ms for r in results), default=0)
        max_mem = max((r.memory_used_kb for r in results), default=0)
        return {"submission_id": job.submission_id, "status": status, "score": total_score,
                "time_used_ms": max_time, "memory_used_kb": max_mem,
                "error_message": error_message, "cases": case_results}

    async def _ensure_data(self, stub, job) -> Path:
        """节点本地缓存命中直接用；否则从网关流式拉取"""
        if self.cache.has(job.problem_id, job.data_version):
            return self.cache.dir_for(job.problem_id, job.data_version)
        metadata = (("x-node-token", self.cfg.server.token),)
        call = stub.FetchProblemData(
            judge_pb2.ProblemDataRequest(problem_id=job.problem_id, data_version=job.data_version),
            metadata=metadata)
        return await self.cache.sync(job.problem_id, job.data_version, call)

    # ---------- 用户自测 ----------

    async def _execute_run_code(self, job: judge_pb2.RunCodeJob):
        async with self.semaphore:
            self.running_tasks += 1
            try:
                limits = ResourceLimits(
                    time_limit_ms=job.limits.time_limit_ms or 5000,
                    memory_limit_mb=job.limits.memory_limit_mb or 256,
                    output_limit_kb=job.limits.output_limit_kb or 1024)
                result = await asyncio.to_thread(
                    self.worker.run_code, job.language, job.code, job.input, limits)
            except Exception as exc:  # noqa: BLE001
                log.exception("自测异常 request=%s", job.request_id)
                result = {"status": "system_error", "output": b"",
                          "error_message": f"node error: {exc}"[:2000]}
            finally:
                self.running_tasks -= 1
        await self.outbox.put(judge_pb2.NodeMessage(run_code_result=judge_pb2.RunCodeResult(
            request_id=job.request_id, status=result["status"],
            output=result["output"], error_message=result.get("error_message", ""),
            time_used_ms=result.get("time_used_ms", 0),
            memory_used_kb=result.get("memory_used_kb", 0))))


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
