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


# ---------------- 判题网关注入（Redis Stream 架构：内存假队列） ----------------

class _FakeJudgeQueue:
    """测试用内存判题队列：替代 Redis Stream（仅实现网关用到的最小子集）。
    任务经 enqueue_judge/enqueue_run 入队，测试用 drain_node_queue 取走；
    结果不走结果 Stream，测试直接调 gw._resolve 唤醒 Future。"""

    def __init__(self):
        self.judge_jobs: list[tuple[str, dict]] = []
        self.run_jobs: list[tuple[str, dict]] = []
        self.results: list[tuple[str, dict]] = []
        self._n = 0

    def _next_id(self, prefix: str) -> str:
        self._n += 1
        return f"{prefix}-{self._n}"

    async def enqueue_judge(self, job: dict) -> str:
        mid = self._next_id("j")
        self.judge_jobs.append((mid, job))
        return mid

    async def enqueue_run(self, job: dict) -> str:
        mid = self._next_id("r")
        self.run_jobs.append((mid, job))
        return mid

    async def publish_result(self, result: dict) -> str:
        mid = self._next_id("res")
        self.results.append((mid, result))
        return mid

    async def consume_results(self, consumer_id, count=10):
        return []

    async def ack_result(self, msg_id):
        pass

    async def queue_stats(self):
        return {"judge_queue_len": len(self.judge_jobs),
                "run_queue_len": len(self.run_jobs),
                "results_queue_len": len(self.results),
                "groups": []}


# 当前 gateway fixture 挂载的假队列（drain_node_queue 取任务用）
_fake_judge_queue: _FakeJudgeQueue | None = None


@pytest_asyncio.fixture()
async def gateway():
    """向 server 模块注入真实 JudgeGatewayServicer（无 gRPC 服务器），
    并把 gateway 模块的 judge_queue 换成内存假实现（测试无 Redis）。
    测试通过 gw._resolve 编排判题结果。"""
    from app.judge_gateway.gateway import JudgeGatewayServicer
    from app.judge_gateway import gateway as gateway_mod
    from app.judge_gateway import server as gw_server

    global _fake_judge_queue
    gw = JudgeGatewayServicer()
    gw_server._gateway = gw
    _fake_judge_queue = _FakeJudgeQueue()
    real_queue = gateway_mod.judge_queue
    gateway_mod.judge_queue = _fake_judge_queue
    yield gw
    gateway_mod.judge_queue = real_queue
    gw_server._gateway = None
    _fake_judge_queue = None


def add_fake_node(gw, node_id: str = "fake-node", capacity: int = 4):
    """向网关注册一个假节点（在线 = out_stream 非空；任务流不走它，走假队列）"""
    from app.judge_gateway.gateway import Node

    node = Node(node_id, "fake", capacity)
    node.out_stream = asyncio.Queue(64)
    node.last_seen = asyncio.get_running_loop().time()
    gw.nodes[node_id] = node
    return node


def active_fake_queue():
    """当前生效的假判题队列（gateway fixture 把真实队列换成的那个实现）。

    以 app.judge_gateway.gateway.judge_queue 为唯一真源：本文件会被 pytest 以
    顶层模块名 `conftest` 加载一次，又被测试文件以包路径 `tests.conftest` 再导入
    一次，两份实例的模块级全局变量互不共享（夹具里赋值的那个全局，测试文件
    import 来的函数读到的却是另一份）。读 app 模块属性天然只有一份。
    """
    from app.judge_gateway import gateway as gateway_mod

    q = gateway_mod.judge_queue
    # 跨实例 isinstance 不可靠（_FakeJudgeQueue 类也是两份），用鸭子类型判定
    if hasattr(q, "judge_jobs") and hasattr(q, "run_jobs"):
        return q
    return None


async def drain_node_queue(node, timeout: float = 2.0):
    """从内存假队列取走全部任务（判题 + 自测），返回 job dict 列表。

    请求任务与入队并发执行：小步轮询，连续 idle 无新任务即认为排空。"""
    queue = active_fake_queue()
    assert queue is not None, "drain_node_queue 需要 gateway fixture"
    jobs: list[dict] = []

    def _drain_all():
        while queue.judge_jobs:
            _mid, job = queue.judge_jobs.pop(0)
            jobs.append(job)
        while queue.run_jobs:
            _mid, job = queue.run_jobs.pop(0)
            jobs.append(job)

    idle_grace = 0.3  # 连续无新任务的静默窗口
    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        before = len(jobs)
        _drain_all()
        if len(jobs) > before:
            await asyncio.sleep(0.02)  # 可能有新任务在途，交出控制权继续收
            continue
        await asyncio.sleep(idle_grace)
        _drain_all()
        if len(jobs) == before:
            break
    return jobs


def _normalize_case(case: dict, *, status: str, time_ms: int, mem_kb: int) -> dict:
    """把用例级结果补齐为节点协议字段（status/time_used_ms/memory_used_kb/score/output）。

    上层读的是 result["cases"][i]["time_used_ms"] 等固定键，测试手写的 case
    可能只给状态与分数，这里统一兜底，避免假数据形状与生产不一致。"""
    c = dict(case)
    c.setdefault("status", status)
    c.setdefault("time_used_ms", time_ms)
    c.setdefault("memory_used_kb", mem_kb)
    c.setdefault("score", 0)
    c.setdefault("output", "")
    return c


async def resolve_submit(gw, job, *, status: str = "accepted", score: int = 100,
                         time_ms: int = 10, mem_kb: int = 8000,
                         error_message: str = "", cases=None):
    """模拟节点回传判题结果：直接调 gw._resolve 唤醒等待中的 submit() Future。
    （Redis Stream 架构下结果本应经结果消费者走到 _resolve，测试短路直达）
    job 为 enqueue 时的 dict（提交/验证/重判共用）。"""
    if cases is None:
        job_cases = job.get("cases", []) if job is not None else []
        cases = [{"test_case_id": c.get("test_case_id")} for c in job_cases]
    # 补齐节点回传 case 的固定字段（生产链路上由 proto → JSON 序列化必然带齐这些键）
    cases = [_normalize_case(c, status=status, time_ms=time_ms, mem_kb=mem_kb)
             for c in cases]
    result = {
        "submission_id": job.get("submission_id") if job is not None else "",
        "status": status, "score": score,
        "time_used_ms": time_ms, "memory_used_kb": mem_kb,
        "error_message": error_message, "cases": cases,
    }
    await gw._resolve(result)
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

    # 标程验证（第二步完成后走第三步）——任务流经内存假队列
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
                                 cases=[{"test_case_id": c["test_case_id"], "status": "accepted"}
                                        for c in job["cases"]])
        r = await asyncio.wait_for(task, timeout=10)
        assert r.status_code == 200, r.text
        assert r.json()["verified"] is True, r.text

    # 发布
    r = await client.put(f"/problems/{p['id']}/publish", json={"is_public": True},
                         headers=await auth_header(user))
    assert r.status_code == 200, r.text
    assert r.json()["is_public"] is True
    return p


# ---------------- AI 助手网关注入（镜像 judge 的 gateway 夹具手法） ----------------

@pytest_asyncio.fixture()
async def assistant_gateway(db_sessionmaker, monkeypatch):
    """向 assistant server 模块注入 AssistantGatewayServicer（无真实 gRPC 服务器）。

    另把 router 模块的 AsyncSessionLocal 指到测试库——SSE 流内自开的会话
    （工具执行 / assistant 落库 / 重载 user）默认连真实 PG，测试必须重定向。"""
    from app.assistant_gateway import server as as_server
    from app.assistant_gateway.gateway import AssistantGatewayServicer
    import app.routers.assistant as assistant_router

    gw = AssistantGatewayServicer()
    as_server._gateway = gw
    monkeypatch.setattr(assistant_router, "AsyncSessionLocal", db_sessionmaker)
    yield gw
    as_server._gateway = None


def add_fake_assistant_node(gw, node_id: str = "fake-assistant", capacity: int = 4):
    """注册一个假助手节点：只挂 out_stream 队列，不真正调 LLM"""
    from app.assistant_gateway.gateway import Node

    node = Node(node_id, "fake", capacity)
    node.out_stream = asyncio.Queue(64)
    node.last_seen = asyncio.get_running_loop().time()
    gw.nodes[node_id] = node
    return node


async def take_assistant_job(node, timeout: float = 2.0):
    """取网关下发给假节点的 ChatJob（ServerMessage.job）"""
    msg = await asyncio.wait_for(node.out_stream.get(), timeout)
    assert msg.HasField("job"), msg
    return msg.job


def push_assistant_events(gw, job, events):
    """模拟节点上行：按序把 ChatDelta/ChatDone/ChatError 路由进 pending 队列，None 哨兵收尾"""
    for evt in events:
        gw._route(job.job_id, evt)
    gw._route(job.job_id, None)


async def take_tool_results(node, count: int, timeout: float = 2.0):
    """收假节点队列里的 ToolResult 回填消息（工具执行后网关发下的）"""
    out = []
    while len(out) < count:
        msg = await asyncio.wait_for(node.out_stream.get(), timeout)
        if msg.HasField("tool_result"):
            out.append(msg.tool_result)
    return out



