# OJ API 服务镜像（生产部署用，构建上下文为仓库根）
# 构建: docker build -f deploy/api.Dockerfile -t oj-api .
# 要点:
#   - WORKDIR 必须 /app（alembic.ini 的 script_location/prepend_sys_path 与 config.py 的
#     env_file=".env" 均相对 CWD，改目录会导致迁移/配置加载失败）
#   - uvicorn 严禁加 --workers：gRPC 网关、节点注册表、雪花 ID 生成器全是进程内状态，
#     多 worker 会破坏判题/助手链路
#   - CMD 先迁移再建管理员再 exec 起服务：任一步失败则不启动，healthy 隐含迁移成功
# 基础镜像默认走代理源（国内直连 docker.io 常被墙）；海外/配了加速器的服务器可
# --build-arg PY_BASE=python:3.12-slim 改回官方
ARG PY_BASE=docker.1ms.run/library/python:3.12-slim
# ${VAR:-default} 兜底：compose 会把未在 build.args 里配置的 ARG 传成空值覆盖默认
FROM ${PY_BASE:-docker.1ms.run/library/python:3.12-slim}

# CN 网络构建可换源（默认清华 PyPI；海外服务器可 --build-arg 改官方）
ARG PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple

WORKDIR /app

# 只拷构建所需（.dockerignore 已排除 .venv/__pycache__ 等）
COPY api/pyproject.toml /app/pyproject.toml
COPY api/app /app/app
COPY api/alembic /app/alembic
COPY api/alembic.ini /app/alembic.ini

RUN pip install --no-cache-dir --index-url ${PIP_INDEX_URL} .

# 判题数据 local 后端兜底目录（生产走 MinIO，仅防意外写入报错）
RUN mkdir -p /app/data

# 8000 HTTP / 50051 判题网关 gRPC / 50060 助手网关 gRPC（节点经 compose 网络连入）
EXPOSE 8000 50051 50060

# 健康检查：slim 镜像无 curl，用 urllib 打 /health
HEALTHCHECK --interval=10s --timeout=5s --retries=10 --start-period=30s \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3).status==200 else 1)"

CMD ["sh", "-c", "alembic upgrade head && python -m app.scripts.create_admin && exec uvicorn app.main:app --host 0.0.0.0 --port 8000"]
