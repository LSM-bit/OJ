# OJ 判题基础镜像（judge-base）
# 文件: deploy/judge-base.Dockerfile
# 用途: 沉淀判题节点"重、慢、极少变"的依赖（C++ 工具链 / JDK21 / Python3.12 / nsjail / gRPC），
#       使 deploy/judge-node.Dockerfile 只做代码 COPY，日常重建几秒完成
# 构建（仓库根目录执行，首次一次即可；改了本文件或要升级依赖时重跑）:
#   docker build -f deploy/judge-base.Dockerfile -t oj-judge-base:24.04 .
# 说明: 本镜像只存在于构建机本地，不由 compose 自动构建；缺它时 judge-node 构建会失败
FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive

# apt 镜像源，可用 --build-arg UBUNTU_MIRROR=... 覆盖：
#   默认阿里云（服务器侧延续原配置，不改动线上行为）
#   本地/国内构建建议华为云 http://repo.huaweicloud.com（实测 7.2MB/s vs 阿里云 0.68MB/s）
# 用 http 而非 https：规避精简构建环境无 ca 证书信任的问题
ARG UBUNTU_MIRROR=http://mirrors.aliyun.com
RUN sed -i "s|http://archive.ubuntu.com|${UBUNTU_MIRROR}|g; s|http://security.ubuntu.com|${UBUNTU_MIRROR}|g" /etc/apt/sources.list.d/* 2>/dev/null || \
    sed -i "s|http://archive.ubuntu.com|${UBUNTU_MIRROR}|g; s|http://security.ubuntu.com|${UBUNTU_MIRROR}|g" /etc/apt/sources.list

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

# 自检：真实编译一个带万能头的程序，确认 g++ 工具链 + 头文件齐备（缺失即构建失败）
# 注意 stdc++.h 在 Debian/Ubuntu 下位于 /usr/include/x86_64-linux-gnu/c++/<ver>/bits/，
# 不在 /usr/include/c++/<ver>/bits/ 下，判题沙箱需挂载 /usr 才能访问
RUN echo '#include <bits/stdc++.h>' > /tmp/t.cpp \
    && echo 'int main(){ return 0; }' >> /tmp/t.cpp \
    && g++ -std=c++17 -O2 -o /tmp/t /tmp/t.cpp \
    && rm -f /tmp/t.cpp /tmp/t \
    && echo "OK: bits/stdc++.h compiles"

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

# 预编译头（PCH）：把 -std=c++17 -O2 下 bits/stdc++.h 的预处理/语法分析结果固化为
# stdc++.h.gch，使每次提交的编译开销从 ~21s 降到数秒。
# 编译选项必须与判题命令一致（-std=c++17 -O2），否则 GCC 会忽略该 PCH 并回退整头解析；
# 不一致时仅忽略+告警，不会导致编译失败，因此不引入正确性风险。
RUN BITS="$(find /usr/include -path '*bits/stdc++.h' | head -1)" \
    && test -n "$BITS" \
    && printf '#include <bits/stdc++.h>\n' > /tmp/pch.cpp \
    && g++ -std=c++17 -O2 -x c++-header /tmp/pch.cpp -o "$BITS.gch" \
    && rm -f /tmp/pch.cpp \
    && ls -l "$BITS.gch" \
    && echo "OK: bits/stdc++.h PCH built"
