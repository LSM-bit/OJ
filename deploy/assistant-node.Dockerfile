# OJ AI 助手节点镜像
# 只做 LLM I/O 中转（Anthropic 流式对话），无沙箱/编译工具链——比判题镜像薄得多
# 基础源走清华/阿里云镜像（构建环境网络受限，同 judge-node.Dockerfile 惯例）
FROM python:3.12-slim

# gRPC 依赖 + Anthropic SDK（pypi 清华镜像）
RUN pip install --no-cache-dir -i https://pypi.tuna.tsinghua.edu.cn/simple \
    grpcio==1.83.0 protobuf==7.36.0 anthropic==0.60.0

WORKDIR /opt/assistant-node
COPY agent/assistant_node/ ./assistant_node/

# key/token 由 compose env 注入（ANTHROPIC_API_KEY / SERVER_ADDRESS / SERVER_TOKEN）
ENV SERVER_ADDRESS="host.docker.internal:50052" \
    SERVER_TOKEN="dev-assistant-token"

CMD ["python", "-m", "assistant_node.daemon", "--config", "assistant_node/node.toml"]
