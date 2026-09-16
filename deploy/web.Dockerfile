# OJ 前端镜像（多阶段：node 构建 → nginx 托管，构建上下文为仓库根）
# 构建: docker build -f deploy/web.Dockerfile --build-arg VITE_API_BASE=/api -t oj-web .
# VITE_API_BASE：生产=/api（nginx 同源反代）；dev 由 Vite 直连 8000，不经此镜像
# 基础镜像默认走代理源（国内直连 docker.io 常被墙）；海外/配了加速器的服务器可
# --build-arg NODE_BASE=node:22-alpine --build-arg NGINX_BASE=nginx:1.27-alpine 改回官方
ARG NODE_BASE=docker.1ms.run/library/node:22-alpine
# ${VAR:-default} 兜底：compose 会把未在 build.args 里配置的 ARG 传成空值覆盖默认
FROM ${NODE_BASE:-docker.1ms.run/library/node:22-alpine} AS build

# Vite 构建时读取 VITE_ 前缀环境变量注入 import.meta.env
ARG VITE_API_BASE=/api

WORKDIR /build
COPY web/package.json web/package-lock.json ./
# CN 网络用 npmmirror（海外服务器可去掉 --registry）
RUN npm ci --registry=https://registry.npmmirror.com

COPY web/ ./
RUN npm run build

ARG NGINX_BASE=docker.1ms.run/library/nginx:1.27-alpine
FROM ${NGINX_BASE:-docker.1ms.run/library/nginx:1.27-alpine}
COPY deploy/nginx/default.conf /etc/nginx/conf.d/default.conf
COPY --from=build /build/dist /usr/share/nginx/html
EXPOSE 80
