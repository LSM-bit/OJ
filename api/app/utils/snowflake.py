"""
snowflake.py - 雪花 ID 生成器

64 位 ID 结构（Twitter Snowflake 变体）：
  1 bit 符号位（恒 0）| 41 bit 毫秒时间戳 | 10 bit 机器 ID | 12 bit 序列号
- 单机线程安全（Lock 保护），多实例部署时用 OJ_SNOWFLAKE_NODE_ID 区分
- 时间回拨 < 5ms 时等待追平；更长则抛错（时钟异常应人工介入）
- 序列号 12 bit：单机单毫秒最多 4096 个 ID
"""

import os
import threading
import time

# 环境变量指定的机器 ID（0-1023），多实例部署时必须互不相同
_NODE_ID = int(os.environ.get("OJ_SNOWFLAKE_NODE_ID", "1")) & 0x3FF

_EPOCH = 1735689600000  # 起始纪元：2025-01-01 00:00:00 UTC（毫秒）

_lock = threading.Lock()
_last_ts = -1
_seq = 0


def next_id() -> int:
    """生成下一个雪花 ID（线程安全）"""
    global _last_ts, _seq
    with _lock:
        ts = int(time.time() * 1000)
        if ts < _last_ts:
            drift = _last_ts - ts
            if drift <= 5:  # 小幅回拨：自旋等待追平
                ts = _last_ts
            else:
                raise RuntimeError(f"系统时钟回拨 {drift}ms，拒绝生成 ID")
        if ts == _last_ts:
            _seq = (_seq + 1) & 0xFFF
            if _seq == 0:  # 当前毫秒序列号用尽，等到下一毫秒
                while ts <= _last_ts:
                    ts = int(time.time() * 1000)
        else:
            _seq = 0
        _last_ts = ts
        return ((ts - _EPOCH) << 22) | (_NODE_ID << 12) | _seq
