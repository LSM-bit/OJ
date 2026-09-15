"""AI 助手网关 gRPC 服务器生命周期（信息：api/app/assistant_gateway/server.py；用途：挂在 FastAPI lifespan 上起停第二个 gRPC server，端口默认 50052）"""

import logging

import grpc

from app.assistant_gateway.gateway import AssistantGatewayServicer
from app.assistant_gateway.gen.assistant.v1 import assistant_pb2_grpc
from app.config import settings

logger = logging.getLogger("assistant-grpc")
_gateway: AssistantGatewayServicer | None = None
_server: grpc.aio.Server | None = None


async def start_assistant_grpc_server() -> None:
    global _gateway, _server
    _gateway = AssistantGatewayServicer()
    _server = grpc.aio.server(
        options=[
            ("grpc.max_receive_message_length", 16 * 1024 * 1024),
            ("grpc.max_send_message_length", 16 * 1024 * 1024),
        ]
    )
    assistant_pb2_grpc.add_AssistantGatewayServicer_to_server(_gateway, _server)
    _server.add_insecure_port(f"[::]:{settings.assistant_grpc_port}")
    await _server.start()
    logger.info("助手网关监听 :%s", settings.assistant_grpc_port)


async def stop_assistant_grpc_server() -> None:
    if _server is not None:
        await _server.stop(grace=2)


def get_assistant_gateway() -> AssistantGatewayServicer:
    """FastAPI 路由获取助手网关实例；未启动时抛 RuntimeError（router 层转 503）"""
    if _gateway is None:
        raise RuntimeError("助手网关未启动")
    return _gateway
