# =============================================================
# 文件: api/app/utils/json_response.py
# 用途: 全局 JSON 响应类 —— 把超过 JS Number 安全整数范围（2^53-1）
#       的大整数（雪花 ID 等）序列化为字符串，防止浏览器 JSON.parse
#       静默丢精度（如 222987058988191744 → ...740 导致 404）。
#       前端拿到字符串 ID 直接回传，Pydantic 会自动 str→int 反序列化。
# =============================================================

import json
from typing import Any

from starlette.responses import JSONResponse

# JavaScript Number.MAX_SAFE_INTEGER = 2^53 - 1
_MAX_SAFE_INT = 9007199254740991


def _convert_big_ints(obj: Any) -> Any:
    """递归遍历响应体，把超出安全范围的大整数转成字符串"""
    if isinstance(obj, dict):
        return {k: _convert_big_ints(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_convert_big_ints(v) for v in obj]
    if isinstance(obj, int) and not isinstance(obj, bool) and abs(obj) > _MAX_SAFE_INT:
        return str(obj)
    return obj


class BigIdJSONResponse(JSONResponse):
    """默认响应类：渲染前先转换大整数 ID"""

    def render(self, content: Any) -> bytes:
        return json.dumps(
            _convert_big_ints(content),
            ensure_ascii=False,
            allow_nan=False,
            indent=None,
            separators=(",", ":"),
        ).encode("utf-8")
