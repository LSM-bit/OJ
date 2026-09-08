"""FastAPI 应用入口"""

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.judge_gateway.server import get_gateway, start_grpc_server, stop_grpc_server
from app.routers import admin, contests, misc, playlists, problems, submissions, teams, users
from app.utils.json_response import BigIdJSONResponse

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await start_grpc_server()
    yield
    await stop_grpc_server()


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    lifespan=lifespan,
    # 雪花 ID 超出 JS Number 安全范围（2^53-1），默认响应类把大整数转字符串
    default_response_class=BigIdJSONResponse,
)

app.include_router(users.router)
app.include_router(problems.router)
app.include_router(submissions.router)
app.include_router(contests.router)
app.include_router(teams.router)
app.include_router(playlists.router)
app.include_router(misc.router)
app.include_router(admin.router)

# 用户头像静态服务：{data 根目录}/avatars → /static/avatars/*（登录后浏览器直接 GET，无鉴权）
_static_avatars = Path(settings.problem_data_dir).parent / "avatars"
_static_avatars.mkdir(parents=True, exist_ok=True)
app.mount("/static/avatars", StaticFiles(directory=str(_static_avatars)), name="avatars")

app.add_middleware(
    CORSMiddleware,
    # localhost 与 127.0.0.1 都放行（浏览器视其为不同源）
    allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$",
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
