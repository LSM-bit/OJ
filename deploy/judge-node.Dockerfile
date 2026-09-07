# OJ 判题节点镜像
# nsjail 沙箱 + 编译工具链 + gRPC 节点守护进程
# 基础源走清华镜像（构建环境网络受限）
FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive
# http 源 + 阿里云镜像（构建环境无 ca 证书信任时 https 会失败）
RUN sed -i 's|http://archive.ubuntu.com|http://mirrors.aliyun.com|g; s|http://security.ubuntu.com|http://mirrors.aliyun.com|g' /etc/apt/sources.list.d/* 2>/dev/null || \
    sed -i 's|http://archive.ubuntu.com|http://mirrors.aliyun.com|g; s|http://security.ubuntu.com|http://mirrors.aliyun.com|g' /etc/apt/sources.list

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3.12 python3-pip \
    g++ gcc \
    openjdk-21-jdk-headless \
    protobuf-compiler \
    && rm -rf /var/lib/apt/lists/*

# nsjail：universe 源缺失，从源码构建（kafel 子模块走 gitee 镜像）
RUN apt-get update && apt-get install -y --no-install-recommends \
    git ca-certificates make autoconf automake libtool pkg-config bison flex \
    libprotobuf-dev protobuf-compiler libnl-route-3-dev libcap-dev \
    && rm -rf /var/lib/apt/lists/* \
    && git clone --depth 1 https://github.com/google/nsjail.git /tmp/nsjail \
    && git clone --depth 1 https://github.com/google/kafel.git /tmp/nsjail/kafel \
    && make -C /tmp/nsjail -j$(nproc) \
    && cp /tmp/nsjail/nsjail /usr/local/bin/nsjail \
    && rm -rf /tmp/nsjail

# gRPC 依赖（pypi 清华镜像）
RUN python3 -m pip install --break-system-packages --no-cache-dir \
    -i https://pypi.tuna.tsinghua.edu.cn/simple \
    grpcio==1.83.0 protobuf==7.36.0

WORKDIR /opt/judge-node
COPY judge/judge_node/ ./judge_node/

RUN mkdir -p /etc/oj /workspace /cache
COPY deploy/nsjail.cfg /etc/oj/nsjail.cfg

ENV SERVER_ADDRESS="host.docker.internal:50051" \
    SERVER_TOKEN="dev-judge-token"

CMD ["python3", "-m", "judge_node.daemon", "--config", "judge_node/node.toml"]
