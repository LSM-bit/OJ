"""gRPC 服务器生命周期管理（挂在 FastAPI lifespan 上）"""

import logging

import grpc

from app.config import settings
from app.judge_gateway.gen.judge.v1 import judge_pb2_grpc
from app.judge_gateway.gateway import JudgeGatewayServicer

logger = logging.getLogger("judge-grpc")
_gateway: JudgeGatewayServicer | None = None
_server: grpc.aio.Server | None = None


async def start_grpc_server(result_sink=None) -> None:
    global _gateway, _server
    _gateway = JudgeGatewayServicer(result_sink=result_sink)
    _server = grpc.aio.server(
        options=[
            ("grpc.max_receive_message_length", 16 * 1024 * 1024),
            ("grpc.max_send_message_length", 16 * 1024 * 1024),
        ]
    )
    judge_pb2_grpc.add_JudgeGatewayServicer_to_server(_gateway, _server)
    _server.add_insecure_port(f"[::]:{settings.judge_grpc_port}")
    await _server.start()
    logger.info("判题网关监听 :%s", settings.judge_grpc_port)


async def stop_grpc_server() -> None:
    if _server is not None:
        await _server.stop(grace=2)


def get_gateway() -> JudgeGatewayServicer:
    """FastAPI 路由获取网关实例"""
    if _gateway is None:
        raise RuntimeError("判题网关未启动")
    return _gateway
