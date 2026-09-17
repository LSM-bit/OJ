"""判题任务 Redis Stream 队列

使用 Redis Stream 持久化判题任务，解决：
1. API 重启任务丢失问题
2. 节点断连任务自动重投
3. 任务 ACK 机制确保不丢任务

Stream 设计：
  oj:judge:queue   - 判题任务主队列，节点 consumer group 消费
  oj:judge:run      - 自测任务队列（低延迟）
  oj:judge:results  - 结果 Stream，网关订阅写库
"""

import asyncio
import json
import logging
import os
from typing import Any

import redis.asyncio as redis

from app.config import settings

logger = logging.getLogger("judge-queue")

# Stream key 常量
STREAM_JUDGE_QUEUE = "oj:judge:queue"
STREAM_JUDGE_RUN = "oj:judge:run"
STREAM_JUDGE_RESULTS = "oj:judge:results"

# Consumer group
GROUP_JUDGE = "judge-nodes"
GROUP_RESULT = "result-consumers"


class JudgeQueue:
    """判题 Redis Stream 队列客户端"""

    def __init__(self, redis_url: str | None = None):
        # 环境变量 > 参数 > settings（支持节点侧覆盖）
        self.redis_url = os.environ.get("REDIS_URL", redis_url or settings.redis_url)
        self._redis: redis.Redis | None = None

    async def connect(self) -> None:
        """建立 Redis 连接"""
        self._redis = redis.from_url(
            self.redis_url,
            decode_responses=True,
            max_connections=10,
        )
        # 初始化 consumer group（忽略已存在错误）
        await self._ensure_groups()
        logger.info("判题队列 Redis 连接建立")

    async def close(self) -> None:
        """关闭连接"""
        if self._redis:
            await self._redis.close()

    async def _ensure_groups(self) -> None:
        """确保 consumer group 存在"""
        for stream, group in [
            (STREAM_JUDGE_QUEUE, GROUP_JUDGE),
            (STREAM_JUDGE_RUN, GROUP_JUDGE),
            (STREAM_JUDGE_RESULTS, GROUP_RESULT),
        ]:
            try:
                await self._redis.xgroup_create(
                    stream, group, id="0", mkstream=True
                )
            except redis.exceptions.ResponseError as e:
                if "BUSYGROUP" not in str(e):
                    raise

    @property
    def r(self) -> redis.Redis:
        if self._redis is None:
            raise RuntimeError("Redis 未连接")
        return self._redis

    # ---------- 判题任务入队 ----------

    async def enqueue_judge(self, job: dict[str, Any]) -> str:
        """提交判题任务到 Stream，返回消息 ID"""
        msg_id = await self.r.xadd(
            STREAM_JUDGE_QUEUE,
            {"data": json.dumps(job, ensure_ascii=False)},
        )
        logger.debug("判题任务入队: submission=%s msg_id=%s",
                     job.get("submission_id"), msg_id)
        return msg_id

    async def enqueue_run(self, job: dict[str, Any]) -> str:
        """提交自测任务到 Stream"""
        msg_id = await self.r.xadd(
            STREAM_JUDGE_RUN,
            {"data": json.dumps(job, ensure_ascii=False)},
        )
        logger.debug("自测任务入队: request=%s msg_id=%s",
                     job.get("request_id"), msg_id)
        return msg_id

    # ---------- 节点消费 ----------

    async def claim_judge(
        self,
        consumer_id: str,
        timeout_ms: int = 5000,
        count: int = 1,
    ) -> list[tuple[str, dict[str, Any]]]:
        """
        判题节点拉取判题任务
        返回: [(msg_id, job_dict), ...]
        """
        # 先投递该 consumer 的 pending 消息（断连重连场景）
        pending = await self._claim_pending(
            STREAM_JUDGE_QUEUE, GROUP_JUDGE, consumer_id, count
        )
        if pending:
            return pending

        # 拉取新消息
        resp = await self.r.xreadgroup(
            GROUP_JUDGE,
            consumer_id,
            {STREAM_JUDGE_QUEUE: ">"},
            count=count,
            block=timeout_ms,
        )
        if not resp:
            return []

        result = []
        for _stream, messages in resp:
            for msg_id, fields in messages:
                job = json.loads(fields.get("data", "{}"))
                result.append((msg_id, job))
        return result

    async def claim_run(
        self,
        consumer_id: str,
        timeout_ms: int = 2000,
        count: int = 1,
    ) -> list[tuple[str, dict[str, Any]]]:
        """判题节点拉取自测任务"""
        pending = await self._claim_pending(
            STREAM_JUDGE_RUN, GROUP_JUDGE, consumer_id, count
        )
        if pending:
            return pending

        resp = await self.r.xreadgroup(
            GROUP_JUDGE,
            consumer_id,
            {STREAM_JUDGE_RUN: ">"},
            count=count,
            block=timeout_ms,
        )
        if not resp:
            return []

        result = []
        for _stream, messages in resp:
            for msg_id, fields in messages:
                job = json.loads(fields.get("data", "{}"))
                result.append((msg_id, job))
        return result

    async def _claim_pending(
        self,
        stream: str,
        group: str,
        consumer_id: str,
        count: int,
    ) -> list[tuple[str, dict[str, Any]]]:
        """投递已 pending（超时未 ACK）的消息"""
        pending = await self.r.xpending_range(
            stream, group, min="-", max="+", count=count, consumername=consumer_id
        )
        if not pending:
            return []

        # 只 claim 静默超过 30s 的消息
        min_idle = 30_000  # ms
        msg_ids = [
            p["message_id"] for p in pending
            if p["time_since_delivered"] > min_idle
        ]
        if not msg_ids:
            return []

        claimed = await self.r.xclaim(
            stream, group, consumer_id, min_idle_time=0, message_ids=msg_ids
        )
        result = []
        for msg_id, fields in claimed:
            if fields:
                job = json.loads(fields.get("data", "{}"))
                result.append((msg_id, job))
        return result

    # ---------- ACK ----------

    async def ack_judge(self, msg_id: str) -> None:
        """确认判题任务完成"""
        await self.r.xack(STREAM_JUDGE_QUEUE, GROUP_JUDGE, msg_id)

    async def ack_run(self, msg_id: str) -> None:
        """确认自测任务完成"""
        await self.r.xack(STREAM_JUDGE_RUN, GROUP_JUDGE, msg_id)

    # ---------- 结果入队 ----------

    async def publish_result(self, result: dict[str, Any]) -> str:
        """发布判题结果到结果 Stream"""
        msg_id = await self.r.xadd(
            STREAM_JUDGE_RESULTS,
            {"data": json.dumps(result, ensure_ascii=False)},
        )
        return msg_id

    # ---------- 结果消费 ----------

    async def consume_results(
        self,
        consumer_id: str,
        count: int = 10,
    ) -> list[tuple[str, dict[str, Any]]]:
        """消费判题结果（网关侧调用）"""
        resp = await self.r.xreadgroup(
            GROUP_RESULT,
            consumer_id,
            {STREAM_JUDGE_RESULTS: ">"},
            count=count,
        )
        if not resp:
            return []

        result = []
        for _stream, messages in resp:
            for msg_id, fields in messages:
                data = json.loads(fields.get("data", "{}"))
                result.append((msg_id, data))
        return result

    async def ack_result(self, msg_id: str) -> None:
        """确认结果已处理"""
        await self.r.xack(STREAM_JUDGE_RESULTS, GROUP_RESULT, msg_id)

    # ---------- 队列监控 ----------

    async def queue_stats(self) -> dict:
        """队列统计"""
        pipe = self.r.pipeline()
        pipe.xlen(STREAM_JUDGE_QUEUE)
        pipe.xlen(STREAM_JUDGE_RUN)
        pipe.xlen(STREAM_JUDGE_RESULTS)
        pipe.xinfo_groups(STREAM_JUDGE_QUEUE)
        lengths = await pipe.execute()

        return {
            "judge_queue_len": lengths[0],
            "run_queue_len": lengths[1],
            "results_queue_len": lengths[2],
            "groups": lengths[3],
        }

    async def clear_pending(self, max_idle_ms: int = 3_600_000) -> int:
        """清理超时未 ACK 的 pending 消息（超过 1 小时的死任务）"""
        cleaned = 0
        for stream in [STREAM_JUDGE_QUEUE, STREAM_JUDGE_RUN]:
            while True:
                pending = await self.r.xpending_range(
                    stream, GROUP_JUDGE, min="-", max="+", count=100
                )
                if not pending:
                    break
                old_ids = [
                    p["message_id"] for p in pending
                    if p["time_since_delivered"] > max_idle_ms
                ]
                if not old_ids:
                    break
                await self.r.xack(
                    stream, GROUP_JUDGE, *old_ids
                )
                cleaned += len(old_ids)
        return cleaned


# 全局队列实例
judge_queue = JudgeQueue()


async def init_judge_queue() -> None:
    """初始化判题队列"""
    await judge_queue.connect()


async def close_judge_queue() -> None:
    """关闭判题队列"""
    await judge_queue.close()
