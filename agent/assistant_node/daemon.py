"""OJ AI 助手节点守护进程（信息：agent/assistant_node/daemon.py；用途：连 API 端助手网关，注册保活，收 ChatJob 交 runner 执行，断线指数退避重连）

用法: python -m assistant_node.daemon --config node.toml
逐段对齐 judge/judge_node/daemon.py 的连接模型（注册→outbox→心跳 10s→退避 1s..30s），
差异仅在任务类型：判题节点跑沙箱，本节点跑 Anthropic 流式对话（见 runner.py）。
"""

import argparse
import asyncio
import contextlib
import logging
import os
import platform
import sys
from pathlib import Path
from types import SimpleNamespace

import grpc

sys.path.insert(0, str(Path(__file__).resolve().parent))

from gen.assistant.v1 import assistant_pb2, assistant_pb2_grpc  # noqa: E402
from runner import ChatSession  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("assistant-node")

# 重连退避：与判题节点一致，1s 起步指数增长封顶 30s，注册成功后清零
RECONNECT_BASE_SECONDS = 1.0
RECONNECT_MAX_SECONDS = 30.0


class AssistantDaemon:
    def __init__(self, cfg):
        self.cfg = cfg
        self.sessions: dict[str, ChatSession] = {}   # job_id -> 在飞会话（回填 ToolResult / 取消用）
        self.running_tasks = 0
        self.backoff = RECONNECT_BASE_SECONDS

    async def run(self):
        """主循环：连接 → 服务 → 断开后指数退避重连"""
        while True:
            try:
                await self._run_once()
            except grpc.aio.AioRpcError as e:
                log.error("连接断开: %s，%.0fs 后重连",
                          e.code(), min(self.backoff, RECONNECT_MAX_SECONDS))
            except Exception:  # noqa: BLE001 未知异常也退避重连，避免进程退出
                log.exception("节点运行异常，%.0fs 后重连", min(self.backoff, RECONNECT_MAX_SECONDS))
            await asyncio.sleep(min(self.backoff, RECONNECT_MAX_SECONDS))
            self.backoff = min(self.backoff * 2, RECONNECT_MAX_SECONDS)

    async def _run_once(self):
        channel = grpc.aio.insecure_channel(self.cfg.server.address)
        stub = assistant_pb2_grpc.AssistantGatewayStub(channel)
        self.outbox: asyncio.Queue = asyncio.Queue(64)

        async def request_gen():
            yield assistant_pb2.NodeMessage(register=assistant_pb2.Register(
                token=self.cfg.server.token,
                node_id=self.cfg.node.id,
                name=self.cfg.node.name or platform.node(),
                capacity=self.cfg.node.capacity,
                version="0.1.0",
            ))
            while True:
                msg = await self.outbox.get()
                yield msg

        heartbeat_task = asyncio.create_task(self._heartbeat_loop())
        log.info("连接助手网关 %s ...", self.cfg.server.address)
        try:
            async for server_msg in stub.Connect(request_gen()):
                if server_msg.HasField("ack"):
                    log.info("注册成功 node_id=%s 心跳=%ss",
                             server_msg.ack.node_id, server_msg.ack.heartbeat_interval_seconds)
                    self.backoff = RECONNECT_BASE_SECONDS
                elif server_msg.HasField("job"):
                    asyncio.create_task(self._execute_job(server_msg.job))
                elif server_msg.HasField("tool_result"):
                    tr = server_msg.tool_result
                    sess = self.sessions.get(tr.job_id)
                    if sess:
                        sess.feed_tool_result(tr)
                    else:
                        log.warning("ToolResult 找不到会话 %s（已结束？）", tr.job_id)
                elif server_msg.HasField("cancel"):
                    sess = self.sessions.get(server_msg.cancel.job_id)
                    if sess:
                        sess.cancel()
        finally:
            with contextlib.suppress(asyncio.CancelledError):
                heartbeat_task.cancel()
                await heartbeat_task
            # 断线即在飞会话全部作废（网关侧已同步以错误收尾）
            for sess in self.sessions.values():
                sess.cancel()
            self.sessions.clear()

    async def _heartbeat_loop(self):
        while True:
            await asyncio.sleep(10)
            await self.outbox.put(assistant_pb2.NodeMessage(
                heartbeat=assistant_pb2.Heartbeat(running_tasks=self.running_tasks)))

    async def _execute_job(self, job: assistant_pb2.ChatJob):
        sess = ChatSession(job, self.cfg, self.outbox)
        self.sessions[job.job_id] = sess
        self.running_tasks += 1
        try:
            await sess.run()
        finally:
            self.running_tasks -= 1
            self.sessions.pop(job.job_id, None)
            log.info("对话 %s 结束（在飞 %d）", job.job_id, self.running_tasks)


def _load_cfg(path: str):
    import tomllib
    with open(path, "rb") as f:
        cfg = tomllib.load(f)
    # 环境变量覆盖（容器部署用）
    env = os.environ
    cfg["server"]["address"] = env.get("SERVER_ADDRESS", cfg["server"]["address"])
    cfg["server"]["token"] = env.get("SERVER_TOKEN", cfg["server"]["token"])
    if env.get("ANTHROPIC_API_KEY"):
        cfg["llm"]["api_key"] = env["ANTHROPIC_API_KEY"]
    if env.get("ASSISTANT_MOCK"):
        cfg["llm"]["mock"] = env["ASSISTANT_MOCK"] == "1"
    return SimpleNamespace(**{
        "server": SimpleNamespace(**cfg["server"]),
        "node": SimpleNamespace(**cfg["node"]),
        "llm": SimpleNamespace(**cfg["llm"]),
    })


def main():
    parser = argparse.ArgumentParser(description="OJ AI 助手节点")
    parser.add_argument("--config", default=str(Path(__file__).with_name("node.toml")))
    args = parser.parse_args()
    cfg = _load_cfg(args.config)
    # mock 模式下无需真实 key；非 mock 时把 key 注入环境供 SDK 读取
    api_key = getattr(cfg.llm, "api_key", "")
    if api_key:
        os.environ["ANTHROPIC_API_KEY"] = api_key
    elif not getattr(cfg.llm, "mock", False) and not os.environ.get("ANTHROPIC_API_KEY"):
        parser.error("未配置 ANTHROPIC_API_KEY（node.toml [llm].api_key 或环境变量），"
                     "联调可用 ASSISTANT_MOCK=1 走 mock 模式")
    asyncio.run(AssistantDaemon(cfg).run())


if __name__ == "__main__":
    main()
