"""FastAPI 应用入口"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.judge_gateway.server import get_gateway, start_grpc_server, stop_grpc_server
from app.routers import problems, submissions, users

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await start_grpc_server()
    yield
    await stop_grpc_server()


app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)

app.include_router(users.router)
app.include_router(problems.router)
app.include_router(submissions.router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health() -> dict:
    """健康检查（Docker/监控用）"""
    return {"status": "ok"}


@app.get("/health/judges")
async def judge_nodes() -> dict:
    """判题节点监控：在线节点数"""
    gw = get_gateway()
    online = [n.node_id for n in gw.nodes.values() if n.out_stream is not None]
    return {"online_nodes": len(online), "nodes": online}


@app.post("/dev/smoke-judge")
async def smoke_judge() -> dict:
    """开发用：判一道 A+B（阶段 1 加鉴权后移除）"""
    from app.judge_gateway.gen.judge.v1 import judge_pb2
    from app.services.problem_data import put_example_data

    code = "s = input().split()\nprint(int(s[0]) + int(s[1]))\n"
    await put_example_data("1", [("tc0", "1 2", "3"), ("tc1", "10 20", "30")])

    job = judge_pb2.SubmitJob(
        submission_id="smoke-1",
        language="python3.12",
        code=code.encode(),
        limits=judge_pb2.ResourceLimits(
            time_limit_ms=2000, memory_limit_mb=256, output_limit_kb=1024, process_limit=32
        ),
        problem_id="1",
        data_version="v1",
        cases=[judge_pb2.TestCase(test_case_id="tc0", score=10),
               judge_pb2.TestCase(test_case_id="tc1", score=10)],
        stop_on_failure=False,
    )
    gw = get_gateway()
    result = await gw.submit(job, timeout=60)
    return {
        "status": result.status,
        "score": result.score,
        "time_used_ms": result.time_used_ms,
        "error_message": result.error_message,
        "cases": [{"id": c.test_case_id, "status": c.status,
                   "time_ms": c.time_used_ms, "mem_kb": c.memory_used_kb}
                  for c in result.cases],
    }
