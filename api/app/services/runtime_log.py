# =============================================================
# 文件: api/app/services/runtime_log.py
# 用途: 运行日志内存环形缓冲——后台「运行日志」页的数据源
#       - RingBufferLogHandler 挂 root logger，捕获全部应用日志
#         （判题网关 / 助手网关 / HTTP 错误 / 业务 INFO）
#       - 内存上限 MAX_ENTRIES 条（常态百 KB ~ MB 级；极端情况全是长异常栈时几十 MB，
#         仍在 api 容器 256M 限额内），满了挤掉最旧；进程重启即清空（定位"现在正在发生什么"够用）
#       - 查询支持级别过滤（error=ERROR+CRITICAL）、关键词、游标分页
# 说明: 单进程部署（uvicorn 单 worker），缓冲区即全量视图；
#       uvicorn.access 不向 root 传播，HTTP 噪声由 main.py 的错误中间件
#       定向补充（只记 >=400），不会刷屏。
# =============================================================

import itertools
import logging
import threading
import traceback
from collections import deque
from datetime import datetime, timezone

MAX_ENTRIES = 2000        # 缓冲容量（条）
MAX_TEXT = 4000           # 单条消息 / 异常栈截断长度
DEFAULT_LIMIT = 200       # 单页默认条数
MAX_LIMIT = 1000          # 单页上限

LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")
_SEVERITY = {name: i for i, name in enumerate(LEVELS)}

_seq = itertools.count(1)          # 全局递增序号，游标分页用
_lock = threading.Lock()
_buffer: deque[dict] = deque(maxlen=MAX_ENTRIES)


class RingBufferLogHandler(logging.Handler):
    """logging.Handler：把记录物化为轻量 dict 存入环形缓冲"""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            entry = {
                "id": next(_seq),
                "ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
                "level": record.levelname,
                "logger": record.name,
                "message": str(record.getMessage())[:MAX_TEXT],
                "exc": self._format_exc(record)[:MAX_TEXT],
            }
            with _lock:
                _buffer.append(entry)
        except Exception:  # noqa: BLE001 日志组件自身绝不能向调用方抛异常
            pass

    @staticmethod
    def _format_exc(record: logging.LogRecord) -> str:
        if not record.exc_info:
            return ""
        if record.exc_info[0] is not None:
            return "".join(traceback.format_exception(*record.exc_info))
        # 只有异常对象没有 traceback
        return "".join(traceback.format_exception_only(record.exc_info[1]))


def install() -> None:
    """挂到 root logger（main.py 启动时调用一次，重复调用幂等）"""
    root = logging.getLogger()
    if any(isinstance(h, RingBufferLogHandler) for h in root.handlers):
        return
    root.addHandler(RingBufferLogHandler(level=logging.INFO))
    logging.getLogger("oj.runtime").info("运行日志缓冲已启动（容量 %d 条）", MAX_ENTRIES)


def query(level: str = "", q: str = "", before: int | None = None,
          limit: int = DEFAULT_LIMIT) -> dict:
    """查询日志：新→旧返回。

    - level: error / warning / info（大小写不敏感，取该级别及以上；
      传空或不认识的全量）
    - q: 关键词，匹配 message / logger / level（小写包含）
    - before: 游标——只返回 id < before 的记录（翻页加载更旧）
    - stats: 整个缓冲的各级别计数（与筛选无关，前端做徽标）
    """
    limit = max(1, min(MAX_LIMIT, limit))
    min_sev = _SEVERITY.get(level.strip().upper(), 0) if level.strip() else 0
    needle = q.strip().lower()

    with _lock:
        snapshot = list(_buffer)

    stats = {"info": 0, "warning": 0, "error": 0}
    out: list[dict] = []
    for e in reversed(snapshot):  # 新 → 旧
        lv = e["level"].lower()
        if lv in stats:
            stats[lv] += 1
        elif lv == "critical":
            stats["error"] += 1
        if _SEVERITY.get(e["level"], 0) < min_sev:
            continue
        if needle:
            haystack = f"{e['message']} {e['logger']} {e['level']}".lower()
            if needle not in haystack:
                continue
        if before is not None and e["id"] >= before:
            continue
        out.append(e)
        if len(out) > limit:  # 多取一条判断 has_more
            break
    has_more = len(out) > limit
    return {"items": out[:limit], "has_more": has_more, "stats": stats}


def clear() -> int:
    """清空缓冲（返回清除条数）"""
    with _lock:
        n = len(_buffer)
        _buffer.clear()
    logging.getLogger("oj.runtime").warning("运行日志缓冲已被管理员清空（%d 条）", n)
    return n
