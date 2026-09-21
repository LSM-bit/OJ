# OJ 前端镜像（多阶段：node 构建 → nginx 托管，构建上下文为仓库根）
# 构建: docker build -f deploy/web.Dockerfile --build-arg VITE_API_BASE=/oj/api -t oj-web .
# 子路径部署：站点对外挂在 /oj/ 下（vite base 在 build 时自动为 /oj/）
#   - VITE_API_BASE=/oj/api：nginx 把 /oj/api/ 前缀剥离后转给 api:8000
#   - dev 由 Vite 直连 8000（vite base = /，可用根路径），不经此镜像
# 基础镜像默认走代理源（国内直连 docker.io 常被墙）；海外/配了加速器的服务器可
# --build-arg NODE_BASE=node:22-alpine --build-arg NGINX_BASE=nginx:1.27-alpine 改回官方
ARG NODE_BASE=docker.1ms.run/library/node:22-alpine
# ${VAR:-default} 兜底：compose 会把未在 build.args 里配置的 ARG 传成空值覆盖默认
FROM ${NODE_BASE:-docker.1ms.run/library/node:22-alpine} AS build

# Vite 构建时读取 VITE_ 前缀环境变量注入 import.meta.env（vite base 在 build 模式下为 /oj/）
ARG VITE_API_BASE=/oj/api

WORKDIR /build
COPY web/package.json web/package-lock.json ./
# CN 网络用 npmmirror（海外服务器可去掉 --registry）
RUN npm ci --registry=https://registry.npmmirror.com

COPY web/ ./
RUN npm run build

ARG NGINX_BASE=docker.1ms.run/library/nginx:1.27-alpine
FROM ${NGINX_BASE:-docker.1ms.run/library/nginx:1.27-alpine}
COPY deploy/nginx/default.conf /etc/nginx/conf.d/default.conf
# 产物落到 html/oj/：与对外 URL 前缀一致，nginx 的 SPA 回退（try_files /oj/index.html）直接可用
COPY --from=build /build/dist /usr/share/nginx/html/oj
EXPOSE 80
