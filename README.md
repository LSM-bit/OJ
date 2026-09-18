<!--
  文件: README.md
  用途: 项目总览——技术栈、目录结构、本地启动、健康检查、对象存储、AI 助手节点
  维护: 新增顶层模块 / 启动方式变化 / 健康检查端口变化后同步更新
-->
# OJ 在线评测系统

面向公网运营的算法竞赛在线评测平台。参考：牛客 OJ / QOJ / Codeforces / 洛谷。

## 技术栈

- **api** — Python 3.12 + FastAPI + SQLAlchemy 2 (async) + Alembic + PostgreSQL + Redis + MinIO
- **judge** — Python 判题编排 + go-judge 沙箱（QOJ/Hydro 同款）
- **agent** — AI 助手独立节点（Anthropic SDK，gRPC 双向流连回 API 内嵌网关）
- **web** — Vue 3 + TypeScript + Vite + Pinia + Element Plus + echarts + markdown-it/KaTeX + Monaco

## 目录结构

```
web/     前端（Vue3：做题/比赛/题单/团队 + 管理后台 13 页，含运行日志）
api/     后端 API（FastAPI，9 个路由模块 + 判题网关 :50051 + 助手网关 :50060）
judge/   判题节点（gRPC 注册/心跳 → nsjail 沙箱执行 → 回写结果）
agent/   AI 助手节点（tool-use 循环，模型 I/O 中转，零 DB/存储访问）
deploy/  docker-compose（dev/prod 双文件）、Dockerfile×4、nginx 配置、密钥模板、nsjail 配置
docs/    架构设计、权限模型、管理后台、AI 助手 Agent、项目计划等设计文档
```

## 本地开发环境启动

Windows 下一键启动：双击根目录 [run.bat](run.bat)（或命令行执行；`run.bat stop` 停容器）。

首次使用先创建 deploy/ 下的三个密钥文件（均已 gitignore）：

```bash
cd deploy
cp api.env.example api.env            # 本机 dev 值即可（Postgres/MinIO 密码 oj_password 等）
echo "SERVER_TOKEN=dev-judge-token" > judge-node.env
# .env 至少三行（真实 LLM key 按需）:
#   ANTHROPIC_API_KEY=...
#   ANTHROPIC_BASE_URL=...（无中转可省）
#   SERVER_TOKEN=dev-assistant-token
```

手动启动：

```bash
# 1. 基础设施 + 两个计算节点（postgres + redis + minio + go-judge 沙箱
#    + judge-node + assistant-node）
cd deploy && docker compose up -d --build

# 2. 后端 API（进程内同时监听 HTTP :8000、判题网关 :50051、助手网关 :50060）
cd api
python -m venv .venv && .venv/Scripts/pip install -e .
.venv/Scripts/alembic upgrade head        # 迁移务必与重启同批（改完不迁移=新表查不到）
.venv/Scripts/uvicorn app.main:app --reload --port 8000

# 3. 前端
cd web
npm install && npm run dev   # http://localhost:5173
```

> AI 助手节点也可不进容器、直接在宿主机起：`cd agent && pip install -e . && python -m assistant_node.daemon`；
> 没配 `ANTHROPIC_API_KEY` 时设 `ASSISTANT_MOCK=1` 走 mock 回显联调（compose 里该服务已留注释开关）。

## 健康检查

本地（dev）：

- API: http://localhost:8000/health
- go-judge 沙箱: http://localhost:5050/version
- 判题节点在线数: http://localhost:8000/health/judges（`{"online_nodes":1,...}` 为已注册）
- MinIO Console: http://localhost:9001（oju / oj_password）
- 前端: http://localhost:5173

生产（全容器化，唯一入口 nginx :80）：`http://域名/api/health`、`http://域名/api/health/judges`。

## 生产部署

API/前端/基础设施全部容器化 + nginx 同源反代（`/api/` 前缀），详见 [docs/服务器部署手册.md](docs/服务器部署手册.md)：

```bash
cd deploy
cp api.env.example api.env   # 填真实密钥（openssl rand -hex 生成，三处一致性见手册）
# judge-node.env / .env 按模板填好
docker compose -f docker-compose.yml -f compose.prod.yml up -d --build
```

要点：对外只暴露 web 容器 80（infra 端口仅 127.0.0.1 绑定）；api 容器 CMD 自带
`alembic upgrade head`（迁移与重启同批由容器天然保证）；uvicorn **必须单 worker**（gRPC
网关/节点注册表/雪花 ID 全在进程内）。

## AI 助手（站内 Agent）

悬浮球对话式助教：能查题面、读用户代码、看判题结果，还能在公开样例上试跑。

- 链路：浏览器 ←SSE← `api/app/routers/assistant.py` ←gRPC← `api/app/assistant_gateway/`（内嵌，:50060）←bidi← `agent/assistant_node`（与判题节点同构）
- 边界：工具执行与权限强制全在 API 侧；节点只做模型 I/O，零 DB/存储访问，Anthropic key 仅存节点 env
- 红线：**比赛进行中参赛者完全禁用**（403 `contest_active`，不做起手式降级）；学生侧永不返回标程与隐藏用例内容（出题者审校面有截断预览例外，见文档）
- 详见 [docs/AI助手Agent设计.md](docs/AI助手Agent设计.md)

## 对象存储（MinIO）

题目测试数据与用户头像存 MinIO（`api/app/services/problem_data.py` 双后端抽象，`storage_backend=minio|local`）：

- `oj-problems` 桶：`{problem_id}-{data_version}/manifest.json` + `cases/tc{N}.in/.out`
- `oj-avatars` 桶：`u{user_id}.{ext}`，经 API 代理端点 `/static/avatars/{filename}` 读取
- 判题节点经 gRPC 流式拉取数据并缓存到本地 `/cache`，无感网关后端介质
- 存量本地数据迁移：`.venv/Scripts/python -m app.scripts.migrate_problem_data_to_minio`

## 测试与质量

```bash
cd api && .venv/Scripts/python -m pytest -q   # 128 个用例（SQLite 临时库 + mock 判题/助手节点）
cd web && npm run build                       # vue-tsc 类型检查 + 构建
```

## 开发阶段

阶段 0（基建）→ 阶段 8（AI 助手二期）已全部完成，进度纪实见 [docs/项目计划.md](docs/项目计划.md)。
