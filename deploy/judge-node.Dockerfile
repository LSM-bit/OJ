# OJ 判题节点镜像（judge-node）
# 重依赖（编译工具链 / JDK21 / Python3.12 / nsjail / gRPC）已沉淀到基础镜像，见 deploy/judge-base.Dockerfile
# 前置（首次部署、或基础镜像更新后，在仓库根目录执行一次）:
#   docker build -f deploy/judge-base.Dockerfile -t oj-judge-base:24.04 .
# 之后本镜像只 COPY 判题节点代码与配置，日常重建只需几秒
FROM oj-judge-base:24.04

WORKDIR /opt/judge-node
COPY judge/judge_node/ ./judge_node/

RUN mkdir -p /etc/oj /workspace /cache
COPY deploy/nsjail.cfg /etc/oj/nsjail.cfg

ENV SERVER_ADDRESS="host.docker.internal:50051" \
    SERVER_TOKEN="dev-judge-token"

CMD ["python3", "-m", "judge_node.daemon", "--config", "judge_node/node.toml"]
