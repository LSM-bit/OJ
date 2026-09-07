"""端到端冒烟测试：判一道 A+B

运行前提：API(8000/50051) 已启动、judge-node 容器已注册、curl 可用。
"""
import httpx
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import settings
from app.judge_gateway.gen.judge.v1 import judge_pb2

API = "http://localhost:8000"

CODE = """s = input().split()
print(int(s[0]) + int(s[1]))
"""


async def main() -> None:
    # 通过 HTTP 触发：/dev/smoke 端点（开发用，阶段1 会加鉴权移除）
    async with httpx.AsyncClient(timeout=90) as client:
        resp = await client.post(f"{API}/dev/smoke-judge")
        resp.raise_for_status()
        data = resp.json()
    print(f"判题结果: {data}")
    assert data["status"] == "accepted", data
    print("冒烟测试通过")


if __name__ == "__main__":
    asyncio.run(main())
