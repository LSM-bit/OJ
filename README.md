# OJ 在线评测系统

面向公网运营的算法竞赛在线评测平台。参考：牛客 OJ / QOJ / Codeforces / 洛谷。

## 技术栈

- **api** — Python 3.12 + FastAPI + SQLAlchemy 2 (async) + Alembic + PostgreSQL + Redis
- **judge** — Python 判题编排 + go-judge 沙箱（QOJ/Hydro 同款）
- **web** — Vue 3 + TypeScript + Vite + Pinia + Element Plus + markdown-it/KaTeX

## 目录结构

```
web/     前端（Vue3）
api/     后端 API（FastAPI）
judge/   判题机（拉取队列任务 → 沙箱执行 → 回写结果）
deploy/  docker-compose、nginx、监控配置
docs/    项目计划、API 文档、判题规则
```

## 本地开发环境启动

```bash
# 1. 基础设施（postgres + redis + go-judge 沙箱）
cd deploy && docker compose up -d

# 2. 后端 API
cd api
python -m venv .venv && .venv/Scripts/pip install -e .
.venv/Scripts/uvicorn app.main:app --reload --port 8000

# 3. 判题机
cd judge
python -m venv .venv && .venv/Scripts/pip install -e .
.venv/Scripts/python -m judge.main

# 4. 前端
cd web
npm install && npm run dev   # http://localhost:5173
```

## 健康检查

- API: http://localhost:8000/health
- go-judge 沙箱: http://localhost:5050/version
- 前端: http://localhost:5173

## 开发阶段

见 [docs/项目计划.md](docs/项目计划.md)（阶段 0 基建 → 阶段 4 公网运营加固）。
