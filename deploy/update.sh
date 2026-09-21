#!/bin/bash
# 服务器更新脚本: 拉代码 -> 需要时重建判题基础镜像 -> 重建并启动全部服务
# 用法（在仓库目录 oj/ 下执行）:
#   bash deploy/update.sh          常规更新（基础镜像缺失时自动构建）
#   bash deploy/update.sh --base   强制重建基础镜像（改了 judge-base.Dockerfile 或升级依赖后）
# 说明: deploy/ 下的密钥文件（api.env / judge-node.env / .env）不在 git 内，pull 不会覆盖它们
set -e

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo "==> [1/3] 拉取最新代码"
git pull --ff-only

if [ "$1" = "--base" ] || ! docker image inspect oj-judge-base:24.04 >/dev/null 2>&1; then
  echo "==> [2/3] 构建判题基础镜像 oj-judge-base:24.04（首次较慢，之后走缓存/直接跳过）"
  docker build -f deploy/judge-base.Dockerfile -t oj-judge-base:24.04 .
else
  echo "==> [2/3] 基础镜像已存在，跳过（需重建请加 --base）"
fi

echo "==> [3/3] 重建并启动服务"
cd deploy
# 迁移兼容（2026-09 容器改名，一次性生效，之后这段是空操作）：
#   早期专属服务的容器名是自动生成的 deploy-<服务>-1；现在改为显式名 deploy-oj-<服务名>。
#   compose 不会自动删掉旧名容器（project 标签相同但配置已不认识它们），而旧容器仍占着
#   web 的 80 端口与网络别名，会导致新容器起不来。这里只删这 4 个专属服务容器：
#   - 未加 -v、未 down，postgres/redis/minio 与数据卷完全不受影响（web/api 等无状态，重建即恢复）
#   - 4 个名字都不存在时报错被忽略，不影响后续启动
docker rm -f deploy-web-1 deploy-api-1 deploy-judge-node-1 deploy-assistant-node-1 2>/dev/null || true
docker compose -f docker-compose.yml -f compose.prod.yml up -d --build
docker compose -f docker-compose.yml -f compose.prod.yml ps
