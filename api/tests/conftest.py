# conftest.py - pytest 全局夹具：SQLite 内存库 + httpx ASGI 客户端 + 判题网关 mock
#
# 设计要点：
# - 每个测试函数独享一个全新 SQLite 内存库（文件型 tmp_path，避免多连接看不到彼此数据）
# - override get_db 依赖指向测试库；Base.metadata.create_all 建表（JSONB 在 SQLite 下降级为 JSON）
# - app.settings.problem_data_dir 指到临时目录，题目数据落 tmp，不污染真实 data/
# - 判题网关不启动真实 gRPC 服务器，直接向 app.judge_gateway.server._gateway 注入
#   JudgeGatewayServicer 实例；submit() 行为由各测试用 fake_gateway 夹具编排
# - lifespan 被禁用（ASGITransport 不触发），避免启动真实 gRPC 监听端口

import asyncio
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.pool import StaticPool
from sqlalchemy.dialects.postgresql import JSONB

from app.database import Base, get_db
from app.models import User, UserRole
from app.services.security import hash_password


@compiles(JSONB, "sqlite")
def _jsonb_sqlite(type_, compiler, **kw):
    return "JSON"


@pytest.fixture()
def data_dir(tmp_path: Path) -> Path:
    """题目数据临时根目录，并让 settings 指向它 + 强制 local 存储后端
    （默认 backend 是 minio，测试不依赖外部 MinIO 服务）"""
    root = tmp_path / "problem_data"
    root.mkdir()
    from app.config import settings

    original_dir = settings.problem_data_dir
    original_backend = settings.storage_backend
    settings.problem_data_dir = str(root)
    settings.storage_backend = "local"
    yield root
    settings.problem_data_dir = original_dir
    settings.storage_backend = original_backend


@pytest_asyncio.fixture()
async def db_engine(tmp_path):
    """独立 SQLite 文件库（StaticPool 单连接共享 + FK 开启）"""
    engine = create_async_engine(
        "sqlite+aiosqlite:///" + str(tmp_path / "test.db"),
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine.sync_engine, "connect")
    def _fk_on(dbapi_conn, _record):
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture()
async def db_sessionmaker(db_engine):
    return async_sessionmaker(db_engine, expire_on_commit=False)


@pytest_asyncio.fixture()
async def client(db_sessionmaker, data_dir):
    """带测试库依赖覆盖的 httpx 异步客户端（未禁用 lifespan，走 TestClient 语义）"""
    from app.main import app

    async def _override_get_db():
        async with db_sessionmaker() as session:
            yield session

    app.dependency_overrides[get_db] = _override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        # 供测试工具函数取 sessionmaker（_LastSessionMaker）
        _sessionmaker_holder.sessionmaker = db_sessionmaker
        yield c
    app.dependency_overrides.pop(get_db, None)


class _sessionmaker_holder:
    sessionmaker = None


def client_sessionmaker():
    """client 夹具对应的 sessionmaker（测试里直接开 DB 会话用）"""
    return _sessionmaker_holder.sessionmaker


# ---------------- 用户快捷注册 ----------------

_user_seq = 0


async def make_user(db, username: str, role: UserRole = UserRole.USER,
                    password: str = "pass123456") -> User:
    """直接在库里造用户（绕过注册接口，测试里更直接）"""
    global _user_seq
    _user_seq += 1
    u = User(
        username=username,
        email=f"{username}{_user_seq}@test.local",
        password_hash=hash_password(password),
        role=role,
    )
    db.add(u)
    await db.commit()
    await db.refresh(u)
    return u


async def auth_header(user: User) -> dict:
    """生成该用户的 Authorization 头"""
    from app.services.security import create_access_token

    token = create_access_token(user.id, user.role.value)
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture()
async def admin_user(db_sessionmaker):
    async with db_sessionmaker() as db:
        return await make_user(db, "admin", UserRole.ADMIN)


@pytest_asyncio.fixture()
async def setter_user(db_sessionmaker):
    """建题权限已放开给所有登录用户（原 PROBLEM_SETTER 角色废弃），用普通用户即可"""
    async with db_sessionmaker() as db:
        return await make_user(db, "setter", UserRole.USER)


@pytest_asyncio.fixture()
async def normal_user(db_sessionmaker):
    async with db_sessionmaker() as db:
        return await make_user(db, "alice", UserRole.USER)


# ---------------- 判题网关注入 ----------------

@pytest_asyncio.fixture()
async def gateway():
    """向 server 模块注入真实 JudgeGatewayServicer（无 gRPC 服务器），返回它。
    测试通过操作 gateway.nodes / gateway.pending 直接编排判题结果。"""
    from app.judge_gateway.gateway import JudgeGatewayServicer
    from app.judge_gateway import server as gw_server

    gw = JudgeGatewayServicer()
    gw_server._gateway = gw
    yield gw
    gw_server._gateway = None


def add_fake_node(gw, node_id: str = "fake-node", capacity: int = 4):
    """向网关注册一个假节点（只挂 out_stream 队列，不真正跑判题）"""
    from app.judge_gateway.gateway import Node

    node = Node(node_id, "fake", capacity, asyncio.Queue(64))
    node.out_stream = node.queue  # 网关下发走 out_stream；测试统一从 node.queue 取
    node.last_seen = asyncio.get_running_loop().time()
    gw.nodes[node_id] = node
    return node


async def drain_node_queue(node, timeout: float = 2.0):
    """取出假节点队列中的 ServerMessage（SubmitJob 等）

    循环 get 直到空（短暂超时即认为队列已空），返回攒到的 job 列表。
    """
    jobs = []
    while True:
        try:
            msg = await asyncio.wait_for(node.out_stream.get(), timeout)
        except (TimeoutError, asyncio.TimeoutError):
            return jobs
        if msg.HasField("job"):
            jobs.append(msg.job)
        elif msg.HasField("run_code"):
            jobs.append(msg.run_code)
        # ack 等其他消息忽略


async def resolve_submit(gw, job, *, status: str = "accepted", score: int = 100,
                         time_ms: int = 10, mem_kb: int = 8000,
                         error_message: str = "", cases=None):
    """模拟节点回传 JudgeResult，唤醒等待中的 submit() Future"""
    from app.judge_gateway.gen.judge.v1 import judge_pb2

    if cases is None:
        if job is not None and job.cases:
            cases = [{"test_case_id": c.test_case_id, "status": status}
                     for c in job.cases]
        else:
            cases = []
    result = judge_pb2.JudgeResult(
        submission_id=job.submission_id if job is not None else "",
        status=status, score=score, time_used_ms=time_ms, memory_used_kb=mem_kb,
        error_message=error_message,
        cases=[judge_pb2.CaseResult(test_case_id=c["test_case_id"],
                                    status=c.get("status", status),
                                    time_used_ms=c.get("time_used_ms", time_ms),
                                    memory_used_kb=c.get("memory_used_kb", mem_kb),
                                    score=c.get("score", 0)) for c in cases],
    )
    gw._resolve(result)
    return result


AC_AB_CODE = "s=input().split()\nprint(int(s[0])+int(s[1]))\n"


async def setup_public_problem(client, user, *, title="A+B",
                               cases=None, ac_code=AC_AB_CODE) -> dict:
    """走完整三步出题流程：创建草稿→传数据→标程验证→发布公开。返回题目 JSON
    数据包只需成对 .in/.out（manifest 由服务端按规则自动生成：非 sample 前缀平分 100 分）"""
    import io
    import zipfile

    r = await client.post("/problems", json={"title": title, "description": "d"},
                          headers=await auth_header(user))
    assert r.status_code == 201, r.text
    p = r.json()
    if cases is None:
        cases = {"tc0": ("1 2", "3"), "tc1": ("10 20", "30")}
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for cid, (i, o) in cases.items():
            zf.writestr(f"{cid}.in", i.encode())
            zf.writestr(f"{cid}.out", o.encode())
    r = await client.post(f"/problems/{p['id']}/data",
                          files={"file": ("d.zip", buf.getvalue(), "application/zip")},
                          headers=await auth_header(user))
    assert r.status_code == 200, r.text

    # 标程验证（第二步完成后走第三步）——需要判题网关有假节点
    from app.judge_gateway.gen.judge.v1 import judge_pb2

    from app.judge_gateway import server as gw_server
    gw = gw_server._gateway
    assert gw is not None, "setup_public_problem 需要 gateway fixture 注入判题网关"
    node = add_fake_node(gw) if not gw.nodes else list(gw.nodes.values())[0]

    async def _verify():
        r = await client.post(f"/problems/{p['id']}/verify",
                              json={"language": "python3.12", "code": ac_code},
                              headers=await auth_header(user))
        return r

    import asyncio
    if True:
        task = asyncio.create_task(_verify())
        jobs = await drain_node_queue(node)
        for job in jobs:
            await resolve_submit(gw, job, status="accepted", score=100,
                                 cases=[{"test_case_id": c.test_case_id, "status": "accepted"}
                                        for c in job.cases])
        r = await asyncio.wait_for(task, timeout=10)
        assert r.status_code == 200, r.text
        assert r.json()["verified"] is True, r.text

    # 发布
    r = await client.put(f"/problems/{p['id']}/publish", json={"is_public": True},
                         headers=await auth_header(user))
    assert r.status_code == 200, r.text
    assert r.json()["is_public"] is True
    return p


