#!/bin/bash
# OJ 项目远程部署脚本
# 在服务器上执行此脚本完成部署
# 使用方法: chmod +x deploy-remote.sh && ./deploy-remote.sh

set -e

PROJECT_DIR="/home/deploy/OJ"
REPO_URL="https://github.com/LSM-bit/OJ.git"

echo "========== OJ 项目部署开始 =========="

# 1. 检查 Docker 环境
if ! command -v docker &> /dev/null; then
    echo "[1/6] 安装 Docker..."
    curl -fsSL https://get.docker.com | sudo sh
    sudo systemctl enable --now docker
    sudo usermod -aG docker $USER
else
    echo "[1/6] Docker 已安装"
fi

if ! docker compose version &> /dev/null; then
    echo "安装 Docker Compose 插件..."
    sudo apt update && sudo apt install -y docker-compose-plugin
fi

# 2. 获取代码
echo "[2/6] 获取代码..."
if [ -d "$PROJECT_DIR" ]; then
    cd "$PROJECT_DIR"
    git pull origin main
else
    cd /home/deploy
    git clone "$REPO_URL"
    cd "$PROJECT_DIR"
fi

# 3. 进入部署目录
cd "$PROJECT_DIR/deploy"

# 4. 配置环境变量
echo "[3/6] 配置环境变量..."
if [ ! -f api.env ]; then
    cp api.env.example api.env

    # 生成随机密钥
    JWT_SECRET=$(openssl rand -hex 32)
    DB_PASSWORD=$(openssl rand -hex 24)
    MINIO_PASSWORD=$(openssl rand -hex 24)
    JUDGE_TOKEN=$(openssl rand -hex 24)
    ASSISTANT_TOKEN=$(openssl rand -hex 24)

    # 替换占位符
    sed -i "s|<openssl rand -hex 32>|$JWT_SECRET|g" api.env
    sed -i "s|<openssl rand -hex 24>|$DB_PASSWORD|g" api.env
    sed -i "s|<同 POSTGRES_PASSWORD>|$DB_PASSWORD|g" api.env
    sed -i "s|<strong密码，登录后尽快更换>|$(openssl rand -hex 8)@OJ|g" api.env

    # MinIO 密码（两个地方）
    sed -i "0,/MINIO_ROOT_PASSWORD=/{s|MINIO_ROOT_PASSWORD=.*|MINIO_ROOT_PASSWORD=$MINIO_PASSWORD|}" api.env
    sed -i "0,/MINIO_SECRET_KEY=/{s|MINIO_SECRET_KEY=.*|MINIO_SECRET_KEY=$MINIO_PASSWORD|}" api.env

    # 节点令牌
    sed -i "s|JUDGE_GATEWAY_TOKENS=\[\"dev-judge-token\"\\]|JUDGE_GATEWAY_TOKENS=\[\"$JUDGE_TOKEN\"\\]|g" api.env
    sed -i "s|ASSISTANT_NODE_TOKENS=\[\"dev-assistant-token\"\\]|ASSISTANT_NODE_TOKENS=\[\"$ASSISTANT_TOKEN\"\\]|g" api.env

    echo "api.env 已生成"
else
    echo "api.env 已存在，跳过生成"
fi

# 判题节点令牌
if [ ! -f judge-node.env ]; then
    JUDGE_TOKEN=$(grep 'JUDGE_GATEWAY_TOKENS' api.env | grep -o '"[^"]*"' | head -1 | tr -d '"')
    echo "SERVER_TOKEN=$JUDGE_TOKEN" > judge-node.env
    echo "judge-node.env 已生成"
fi

# AI 助手节点
if [ ! -f .env ]; then
    ASSISTANT_TOKEN=$(grep 'ASSISTANT_NODE_TOKENS' api.env | grep -o '"[^"]*"' | head -1 | tr -d '"')
    cat > .env << EOF
SERVER_TOKEN=$ASSISTANT_TOKEN
# ANTHROPIC_API_KEY=你的密钥（可选，不填则助手不可用）
EOF
    echo ".env 已生成（AI 助手需手动添加 ANTHROPIC_API_KEY）"
fi

# 5. 构建并启动服务
echo "[4/6] 构建并启动服务..."
docker compose -f docker-compose.yml -f compose.prod.yml down 2>/dev/null || true
docker compose -f docker-compose.yml -f compose.prod.yml up -d --build

# 6. 等待并验证
echo "[5/6] 等待服务启动..."
sleep 15

echo "[6/6] 验证部署..."
docker compose -f docker-compose.yml -f compose.prod.yml ps

echo ""
echo "========== 部署完成 =========="
echo "请确认所有服务状态为 'Up' 或 'healthy'"
echo "访问: http://$(curl -s ifconfig.me)"
echo ""
echo "检查判题节点: curl http://localhost/api/health/judges"
echo ""
echo "如需查看日志: docker compose -f docker-compose.yml -f compose.prod.yml logs -f api judge-node"
