"""OJ AI 助手节点·对话执行器（信息：agent/assistant_node/runner.py；用途：单个 ChatJob 的生命周期——以 stream=True 调 Anthropic，逐 token 把增量 put 到 outbox，工具轮等 API 侧回填 ToolResult 后续轮）

边界（与网关契约一致）：
- 节点只做模型 I/O 中转：不执行工具、零 DB/存储访问，Anthropic key 仅存本进程；
- 全程逐 token 透传：文本增量即时包 ChatDelta{text_chunk}，工具调用块完成后包
  ChatDelta{tool_use}，done 仅在整轮（含所有工具往返）结束后发出；
- mock 模式（node.toml [llm] mock=true 或 env ASSISTANT_MOCK=1）不调 Anthropic，
  回显预设文本，用于链路联调与 CI。
"""

import asyncio
import json
import logging
import os
import time

from gen.assistant.v1 import assistant_pb2

log = logging.getLogger("assistant-runner")

MAX_TURNS = 8           # 单轮对话内工具往返上限（与设计文档 §4 一致）
TOTAL_TIMEOUT = 120.0   # 单 job 总超时（秒）


def _delta(job_id: str, **kwargs) -> assistant_pb2.NodeMessage:
    return assistant_pb2.NodeMessage(delta=assistant_pb2.ChatDelta(job_id=job_id, **kwargs))


class ChatSession:
    """一个 ChatJob 的会话态：messages 演进 + 待回填 tool_use 的 Future 表"""

    def __init__(self, job: assistant_pb2.ChatJob, cfg, outbox: asyncio.Queue):
        self.job = job
        self.cfg = cfg
        self.outbox = outbox
        self.pending_tools: dict[str, asyncio.Future] = {}
        self.cancelled = False
        self.finished = False

    # ---------- daemon 侧入口 ----------

    async def run(self) -> None:
        """执行整轮对话，无论成败最终以 ChatDone / ChatError 收尾"""
        job_id = self.job.job_id
        try:
            if self.mock_mode():
                await self._run_mock()
            else:
                await self._run_llm()
        except asyncio.CancelledError:
            await self._emit_error("对话已取消")
            raise
        except Exception as exc:  # noqa: BLE001 模型侧异常统一转 ChatError（脱敏）
            log.exception("job %s 执行异常", job_id)
            await self._emit_error(f"助手节点错误: {exc.__class__.__name__}")
        finally:
            self.finished = True
            for fut in self.pending_tools.values():
                if not fut.done():
                    fut.cancel()

    def feed_tool_result(self, tr: assistant_pb2.ToolResult) -> None:
        fut = self.pending_tools.pop(tr.tool_use_id, None)
        if fut and not fut.done():
            fut.set_result((tr.content_json, tr.is_error))

    def cancel(self) -> None:
        self.cancelled = True
        for fut in self.pending_tools.values():
            if not fut.done():
                fut.set_exception(RuntimeError("cancelled"))

    @staticmethod
    def mock_mode() -> bool:
        return os.environ.get("ASSISTANT_MOCK") == "1"

    # ---------- 真模型路径 ----------

    async def _run_llm(self) -> None:
        from anthropic import AsyncAnthropic

        job = self.job
        client = AsyncAnthropic()  # key 走环境变量 ANTHROPIC_API_KEY
        msgs = json.loads(job.messages_json or "[]")
        tools = json.loads(job.tools_json or "[]")
        model = job.model or self.cfg.llm.default_model
        max_tokens = job.max_tokens or getattr(self.cfg.llm, "max_tokens", 4096)

        all_blocks: list[dict] = []   # 各轮 assistant blocks（落库回放用）
        usage_in = usage_out = 0
        deadline = time.monotonic() + TOTAL_TIMEOUT
        stop_reason = "end_turn"

        for _turn in range(MAX_TURNS):
            if self.cancelled:
                await self._emit_error("对话已取消")
                return
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                stop_reason = "timeout"
                break

            blocks, msg_stop, usage_in, usage_out = await self._stream_once(
                client, model, max_tokens, msgs, tools, usage_in, usage_out)
            all_blocks.extend(blocks)

            tool_uses = [b for b in blocks if b.get("type") == "tool_use"]
            if msg_stop != "tool_use" or not tool_uses:
                stop_reason = msg_stop
                break

            # 逐工具请求：上行 ToolUse → 等 API 侧回填 → 组 tool_result
            msgs.append({"role": "assistant", "content": blocks})
            results = []
            for tu in tool_uses:
                if self.cancelled:
                    await self._emit_error("对话已取消")
                    return
                await self.outbox.put(_delta(
                    job.job_id,
                    tool_use=assistant_pb2.ToolUse(
                        id=tu["id"], name=tu["name"],
                        input_json=json.dumps(tu.get("input", {}), ensure_ascii=False))))
                fut = asyncio.get_running_loop().create_future()
                self.pending_tools[tu["id"]] = fut
                try:
                    content_json, is_error = await asyncio.wait_for(
                        fut, timeout=max(deadline - time.monotonic(), 1))
                except (asyncio.TimeoutError, RuntimeError):
                    content_json = json.dumps({"error": "工具执行超时或已取消"})
                    is_error = True
                finally:
                    self.pending_tools.pop(tu["id"], None)
                results.append({
                    "type": "tool_result", "tool_use_id": tu["id"],
                    "content": json.loads(content_json), "is_error": is_error,
                })
            msgs.append({"role": "user", "content": results})
        else:
            stop_reason = "max_turns"

        await self.outbox.put(assistant_pb2.NodeMessage(done=assistant_pb2.ChatDone(
            job_id=job.job_id,
            content_json=json.dumps(all_blocks, ensure_ascii=False),
            input_tokens=usage_in, output_tokens=usage_out,
            stop_reason=stop_reason)))

    async def _stream_once(self, client, model, max_tokens, msgs, tools,
                           usage_in, usage_out):
        """一次 messages.stream 调用：文本增量即时上行；返回 (assistant_blocks, stop_reason, 累计用量)"""
        job = self.job
        kwargs = {}
        if tools:
            kwargs["tools"] = tools
        async with client.messages.stream(
            model=model, max_tokens=max_tokens, system=job.system or "",
            messages=msgs, **kwargs,
        ) as stream:
            async for event in stream:
                if self.cancelled:
                    break
                evt = getattr(event, "type", "")
                if evt == "content_block_delta":
                    delta = event.delta
                    if getattr(delta, "type", "") == "text_delta" and delta.text:
                        await self.outbox.put(_delta(job.job_id, text_chunk=delta.text))
            final = await stream.get_final_message()
        blocks = [b.model_dump(exclude_none=True) if hasattr(b, "model_dump") else dict(b)
                  for b in final.content]
        usage_in += final.usage.input_tokens
        usage_out += final.usage.output_tokens
        return blocks, final.stop_reason or "end_turn", usage_in, usage_out

    # ---------- mock 路径（不联网，验证流式链路） ----------

    async def _run_mock(self) -> None:
        """逐块回显最后一条 user 消息；若带工具声明则模拟一轮 get_my_stats 往返"""
        job = self.job
        msgs = json.loads(job.messages_json or "[]")
        last_user = ""
        for m in reversed(msgs):
            if m.get("role") == "user":
                c = m.get("content")
                last_user = c if isinstance(c, str) else json.dumps(c, ensure_ascii=False)
                break
        reply = f"[mock] 已收到你的消息：{last_user[:200]}"
        # 模拟逐 token：每 4 字符一个增量
        chunks = [reply[i:i + 4] for i in range(0, len(reply), 4)] or [reply]
        full = []
        for ch in chunks:
            await asyncio.sleep(0.01)
            await self.outbox.put(_delta(job.job_id, text_chunk=ch))
            full.append(ch)
        await self.outbox.put(assistant_pb2.NodeMessage(done=assistant_pb2.ChatDone(
            job_id=job.job_id,
            content_json=json.dumps([{"type": "text", "text": "".join(full)}],
                                    ensure_ascii=False),
            input_tokens=len(last_user) // 4, output_tokens=len(reply) // 4,
            stop_reason="end_turn")))

    async def _emit_error(self, message: str) -> None:
        await self.outbox.put(assistant_pb2.NodeMessage(error=assistant_pb2.ChatError(
            job_id=self.job.job_id, message=message[:500])))
