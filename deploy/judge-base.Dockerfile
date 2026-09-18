# OJ 判题基础镜像（judge-base）
# 文件: deploy/judge-base.Dockerfile
# 用途: 沉淀判题节点"重、慢、极少变"的依赖（C++ 工具链 / JDK21 / Python3.12 / nsjail / gRPC），
#       使 deploy/judge-node.Dockerfile 只做代码 COPY，日常重建几秒完成
# 构建（仓库根目录执行，首次一次即可；改了本文件或要升级依赖时重跑）:
#   docker build -f deploy/judge-base.Dockerfile -t oj-judge-base:24.04 .
# 说明: 本镜像只存在于构建机本地，不由 compose 自动构建；缺它时 judge-node 构建会失败
FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive
# http 源 + 阿里云镜像（构建环境无 ca 证书信任时 https 会失败）
RUN sed -i 's|http://archive.ubuntu.com|http://mirrors.aliyun.com|g; s|http://security.ubuntu.com|http://mirrors.aliyun.com|g' /etc/apt/sources.list.d/* 2>/dev/null || \
    sed -i 's|http://archive.ubuntu.com|http://mirrors.aliyun.com|g; s|http://security.ubuntu.com|http://mirrors.aliyun.com|g' /etc/apt/sources.list

# 运行时依赖: Python 3.12 / C++ 工具链 / JDK 21 / protobuf
# apt 目录挂宿主缓存（BuildKit cache mount）: 本层失效时 deb 仍在缓存里，只做本地安装，
# 省掉数百 MB 重复下载——这是原先每次重建都卡 40s+ 的根因
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update && apt-get install -y --no-install-recommends \
    python3.12 python3-pip \
    g++ gcc \
    openjdk-21-jdk-headless \
    protobuf-compiler

# nsjail: universe 源缺失，从源码构建（kafel 子模块单独 clone）
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update && apt-get install -y --no-install-recommends \
    git ca-certificates make autoconf automake libtool pkg-config bison flex \
    libprotobuf-dev protobuf-compiler libnl-route-3-dev libcap-dev \
    && git clone --depth 1 https://github.com/google/nsjail.git /tmp/nsjail \
    && git clone --depth 1 https://github.com/google/kafel.git /tmp/nsjail/kafel \
    && make -C /tmp/nsjail -j"$(nproc)" \
    && cp /tmp/nsjail/nsjail /usr/local/bin/nsjail \
    && rm -rf /tmp/nsjail

# gRPC + Redis 依赖（pypi 清华镜像）
RUN python3 -m pip install --break-system-packages --no-cache-dir \
    -i https://pypi.tuna.tsinghua.edu.cn/simple \
    grpcio==1.83.0 protobuf==7.36.0 'redis>=5.2'
