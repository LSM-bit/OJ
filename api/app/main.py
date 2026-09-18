"""FastAPI 应用入口"""

import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response

from app.assistant_gateway.server import (get_assistant_gateway,
                                          start_assistant_grpc_server,
                                          stop_assistant_grpc_server)
from app.config import settings
from app.judge_gateway.server import get_gateway, start_grpc_server, stop_grpc_server
from app.routers import (admin, assistant, contests, misc, playlists, problems,
                         submissions, teams, users)
from app.services import problem_data
from app.services import runtime_log
from app.utils.json_response import BigIdJSONResponse

logging.basicConfig(level=logging.INFO)
# 运行日志环形缓冲：后台「运行日志」页数据源（越早装上，启动期日志越全）
runtime_log.install()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await start_grpc_server()
    await start_assistant_grpc_server()
    yield
    await stop_assistant_grpc_server()
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
app.include_router(assistant.router)

# 用户头像服务：MinIO 读取后经 API 代理下发（URL 保持 /static/avatars/*，前端零改动）
_AVATAR_CONTENT_TYPES = {"jpg": "image/jpeg", "png": "image/png",
                         "webp": "image/webp", "gif": "image/gif"}


@app.get("/static/avatars/{filename}")
async def avatar(filename: str) -> Response:
    data = await problem_data.get_avatar(filename)
    if data is None:
        from fastapi import HTTPException, status
        raise HTTPException(status.HTTP_404_NOT_FOUND, "头像不存在")
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    media_type = _AVATAR_CONTENT_TYPES.get(ext, "application/octet-stream")
    # 缓存一小时：头像文件名 per 用户固定（覆盖写），短缓存避免更新后浏览器还用旧图
    return Response(content=data, media_type=media_type,
                    headers={"Cache-Control": "public, max-age=3600"})

@app.middleware("http")
async def log_http_errors(request, call_next):
    """HTTP 错误定向进运行日志：>=400 的请求一行 WARNING/ERROR（含耗时）。
    uvicorn access log 不向 root 传播，这里只补错误请求，正常请求不刷屏；
    未捕获异常栈也落日志，后台可免 SSH 排障。"""
    t0 = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        logging.getLogger("oj.http").error(
            "HTTP 500 %s %s（未捕获异常）", request.method, request.url.path,
            exc_info=True)
        raise
    if response.status_code >= 400:
        ms = (time.perf_counter() - t0) * 1000
        log = logging.getLogger("oj.http")
        if response.status_code >= 500:
            log.error("HTTP %d %s %s %.0fms", response.status_code,
                      request.method, request.url.path, ms)
        else:
            log.warning("HTTP %d %s %s %.0fms", response.status_code,
                        request.method, request.url.path, ms)
    return response


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
