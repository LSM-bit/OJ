"""测试题目模块：创建 / 列表可见性 / 详情 / 数据包上传 / 权限边界"""

import io
import json
import zipfile

import pytest
from httpx import AsyncClient

from tests.conftest import auth_header

pytestmark = pytest.mark.asyncio


def problem_payload(**kw) -> dict:
    # 创建接口不再接收 is_public（新题一律草稿）；is_public 仅用于标记期望走发布流程
    body = {"title": kw.get("title", "A+B Problem"), "description": kw.get("description", "# 题面"),
            "difficulty": kw.get("difficulty", 1), "tags": kw.get("tags", ["入门"]),
            "time_limit_ms": kw.get("time_limit_ms", 2000), "memory_limit_mb": kw.get("memory_limit_mb", 256)}
    return body


async def _create_problem(client, user, **kw) -> dict:
    """创建题目；若 is_public=True 则走完整三步出题（数据+验证+发布），否则保持草稿"""
    r = await client.post("/problems", json=problem_payload(**kw),
                          headers=await auth_header(user))
    assert r.status_code == 201, r.text
    p = r.json()
    # 注意：只有 is_public=True 才走发布流程（需要 gateway fixture）；默认草稿
    return p


def make_zip(manifest: dict | None = None, extra: dict[str, bytes] | None = None) -> bytes:
    """构造题目数据 zip 包"""
    if manifest is None:
        manifest = {"cases": [{"id": "tc0", "score": 50}, {"id": "tc1", "score": 50}]}
    files = {"manifest.json": json.dumps(manifest).encode(),
             "cases/tc0.in": b"1 2", "cases/tc0.out": b"3",
             "cases/tc1.in": b"10 20", "cases/tc1.out": b"30"}
    if extra:
        files.update(extra)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, content in files.items():
            zf.writestr(name, content)
    return buf.getvalue()


# ---------------- 创建与列表 ----------------

async def test_create_problem_requires_auth(client: AsyncClient):
    r = await client.post("/problems", json=problem_payload())
    assert r.status_code == 401


async def test_create_and_get_problem(client, normal_user):
    p = await _create_problem(client, normal_user)
    assert p["title"] == "A+B Problem"
    assert p["time_limit_ms"] == 2000
    assert p["display_id"] >= 1

    # 草稿对 owner 可见
    r = await client.get(f"/problems/{p['id']}", headers=await auth_header(normal_user))
    assert r.status_code == 200
    assert r.json()["description"] == "# 题面"


async def test_publish_flow_makes_problem_public(client, normal_user, gateway):
    """三步出题：草稿→数据→标程验证→发布公开后匿名可见"""
    from tests.conftest import setup_public_problem
    p = await setup_public_problem(client, normal_user, title="published")
    r = await client.get(f"/problems/{p['id']}")  # 匿名
    assert r.status_code == 200, r.text
    assert r.json()["is_public"] is True


async def test_problem_list_visibility(client, normal_user, setter_user, admin_user, db_sessionmaker, gateway):
    """公开题所有人可见；私有题仅 owner 与 ADMIN 可见"""
    from tests.conftest import setup_public_problem
    pub = await setup_public_problem(client, normal_user, title="public")
    priv = await _create_problem(client, normal_user, title="private")

    # 未登录：只见公开
    r = await client.get("/problems")
    titles = {x["title"] for x in r.json()}
    assert "public" in titles and "private" not in titles

    # owner（登录）：默认列表仍只见公开；mine=1 出题视角可见自己的私有草稿
    r = await client.get("/problems", headers=await auth_header(normal_user))
    titles = {x["title"] for x in r.json()}
    assert "public" in titles and "private" not in titles
    r = await client.get("/problems?mine=1", headers=await auth_header(normal_user))
    titles = {x["title"] for x in r.json()}
    assert {"public", "private"} <= titles

    # 其他普通用户：只见公开
    from tests.conftest import make_user
    async with db_sessionmaker() as db:
        other = await make_user(db, "other_user")
    r = await client.get("/problems", headers=await auth_header(other))
    titles = {x["title"] for x in r.json()}
    assert "public" in titles and "private" not in titles

    # ADMIN：mine=1 出题视角全见
    r = await client.get("/problems?mine=1", headers=await auth_header(admin_user))
    titles = {x["title"] for x in r.json()}
    assert {"public", "private"} <= titles


async def test_private_problem_detail_hidden_from_others(client, normal_user, db_sessionmaker):
    priv = await _create_problem(client, normal_user, title="secret", is_public=False)

    from tests.conftest import make_user
    async with db_sessionmaker() as db:
        other = await make_user(db, "peeker")

    # 无权者按 404 处理（防枚举）
    r = await client.get(f"/problems/{priv['id']}", headers=await auth_header(other))
    assert r.status_code == 404
    # owner 可见
    r = await client.get(f"/problems/{priv['id']}", headers=await auth_header(normal_user))
    assert r.status_code == 200


# ---------------- 数据包上传 ----------------

async def test_upload_data_and_manifest_sync(client, normal_user):
    p = await _create_problem(client, normal_user)
    r = await client.post(f"/problems/{p['id']}/data",
                          files={"file": ("data.zip", make_zip(), "application/zip")},
                          headers=await auth_header(normal_user))
    assert r.status_code == 200, r.text
    assert r.json()["cases"] == 2

    # 数据文件确实落盘
    from app.services.problem_data import data_dir
    from app.config import settings
    root = data_dir(str(p["id"]), "v1")
    assert (root / "manifest.json").is_file()
    assert (root / "cases" / "tc0.in").is_file()


async def test_upload_data_missing_case_file(client, normal_user):
    """manifest 声明了 tc2 但包里没有 → 400"""
    p = await _create_problem(client, normal_user)
    bad_zip = make_zip(manifest={"cases": [{"id": "tc2", "score": 100}]})
    r = await client.post(f"/problems/{p['id']}/data",
                          files={"file": ("data.zip", bad_zip, "application/zip")},
                          headers=await auth_header(normal_user))
    assert r.status_code == 400


async def test_upload_data_requires_manage_permission(client, normal_user, db_sessionmaker):
    p = await _create_problem(client, normal_user)
    from tests.conftest import make_user
    async with db_sessionmaker() as db:
        other = await make_user(db, "not_owner")

    r = await client.post(f"/problems/{p['id']}/data",
                          files={"file": ("data.zip", make_zip(), "application/zip")},
                          headers=await auth_header(other))
    assert r.status_code == 404  # 无管理权按不存在处理


async def test_upload_invalid_zip(client, normal_user):
    p = await _create_problem(client, normal_user)
    r = await client.post(f"/problems/{p['id']}/data",
                          files={"file": ("data.zip", b"not a zip", "application/zip")},
                          headers=await auth_header(normal_user))
    assert r.status_code == 400


# ---------------- 编辑 ----------------

async def test_update_problem_by_owner(client, normal_user):
    p = await _create_problem(client, normal_user)
    r = await client.put(f"/problems/{p['id']}", json={"title": "renamed", "difficulty": 3},
                         headers=await auth_header(normal_user))
    assert r.status_code == 200, r.text
    assert r.json()["title"] == "renamed"
    assert r.json()["difficulty"] == 3


async def test_update_problem_denied_for_others(client, normal_user, db_sessionmaker):
    p = await _create_problem(client, normal_user)
    from tests.conftest import make_user
    async with db_sessionmaker() as db:
        other = await make_user(db, "editor_wannabe")
    r = await client.put(f"/problems/{p['id']}", json={"title": "hacked"},
                         headers=await auth_header(other))
    assert r.status_code == 404


# ---------------- 标签筛选与标签云 ----------------

async def _make_public_problem(client, user, *, title: str, tags: list[str]) -> dict:
    """造一道公开题：先创建（带 tags），走数据上传 + 标程验证 + 发布。
    复用 test_publish_flow_makes_problem_public 的流程，仅注入 tags"""
    r = await client.post("/problems", json=problem_payload(title=title, tags=tags),
                          headers=await auth_header(user))
    assert r.status_code == 201, r.text
    p = r.json()
    r = await client.post(f"/problems/{p['id']}/data",
                          files={"file": ("data.zip", make_zip(), "application/zip")},
                          headers=await auth_header(user))
    assert r.status_code == 200, r.text

    from app.judge_gateway.gen.judge.v1 import judge_pb2

    from app.judge_gateway import server as gw_server
    from tests.conftest import add_fake_node, drain_node_queue, resolve_submit
    gw = gw_server._gateway
    node = add_fake_node(gw) if not gw.nodes else list(gw.nodes.values())[0]

    import asyncio

    async def _verify():
        return await client.post(f"/problems/{p['id']}/verify",
                                 json={"language": "python3.12", "code": "print(sum(map(int, input().split())))"},
                                 headers=await auth_header(user))

    task = asyncio.create_task(_verify())
    jobs = await drain_node_queue(node)
    for job in jobs:
        await resolve_submit(gw, job, status="accepted", score=100,
                             cases=[{"test_case_id": c.test_case_id, "status": "accepted"} for c in job.cases])
    r = await asyncio.wait_for(task, timeout=10)
    assert r.status_code == 200 and r.json()["verified"] is True, r.text

    r = await client.put(f"/problems/{p['id']}/publish", json={"is_public": True},
                         headers=await auth_header(user))
    assert r.status_code == 200, r.text
    return p


async def test_problem_tag_filter(client, normal_user, gateway):
    """?tag= 单标签过滤；多标签逗号分隔取交集；草稿不参与"""
    from tests.conftest import AC_AB_CODE, setup_public_problem

    # setup_public_problem 创建的题不带 tags（默认空），先造三道不同标签的公开题
    sim = await _make_public_problem(client, normal_user, title="模拟题", tags=["模拟", "暴力"])
    math = await _make_public_problem(client, normal_user, title="数学题", tags=["数学"])
    both = await _make_public_problem(client, normal_user, title="模拟数学题", tags=["模拟", "数学"])
    # 一道私有草稿：不应出现在任何筛选结果里
    await _create_problem(client, normal_user, title="草稿题", tags=["模拟"])

    # 单标签
    r = await client.get("/problems", params={"tag": "模拟"})
    titles = {x["title"] for x in r.json()}
    assert titles == {"模拟题", "模拟数学题"}
    assert all("模拟" in x["tags"] for x in r.json())

    # 多标签取交集：模拟 ∧ 数学 只有 both
    r = await client.get("/problems", params={"tag": "模拟,数学"})
    titles = {x["title"] for x in r.json()}
    assert titles == {"模拟数学题"}
    # 两题结果集 id 与创建顺序一致
    assert [x["id"] for x in r.json()] == [both["id"]]

    # 不存在的标签：空列表
    r = await client.get("/problems", params={"tag": "不存在"})
    assert r.json() == []

    # 不带 tag：公开题全集（3 道公开，草稿不出现）
    r = await client.get("/problems")
    titles = {x["title"] for x in r.json()}
    assert titles == {"模拟题", "数学题", "模拟数学题"}


async def test_tag_cloud_counts_only_public(client, normal_user, gateway):
    """GET /problems/tags 只统计公开题；计数降序；同题内标签各计一次"""
    from tests.conftest import setup_public_problem
    await _make_public_problem(client, normal_user, title="t1", tags=["模拟", "模拟", "数学"])
    # 私有草稿带标签：不计入标签云
    await _create_problem(client, normal_user, title="t2-draft", tags=["模拟", "独家"])

    r = await client.get("/problems/tags")
    assert r.status_code == 200, r.text
    items = r.json()["items"]
    counter = {x["tag"]: x["count"] for x in items}
    # 重复标签去重后计 1；草稿标签不出现
    assert counter == {"模拟": 1, "数学": 1}
    # 计数相同按 tag 字典序
    assert [x["tag"] for x in items] == ["数学", "模拟"]


# ---------------- 归档 ----------------

async def test_archive_problem_flow(client, normal_user, db_sessionmaker, gateway):
    """题目归档全链路：列表隐藏 → 刷题/管理视角都看不到 → archived=1 可见 →
    详情可访问但不可提交 → 恢复后一切照旧"""
    from tests.conftest import make_user

    p = await _create_problem(client, normal_user, title="归档题")

    # 归档需要管理权：陌生人不允许（私有草稿题按不存在处理，防枚举）
    async with db_sessionmaker() as db:
        stranger = await make_user(db, "arch_stranger")
    r = await client.put(f"/problems/{p['id']}/archive", json={"archived": True},
                         headers=await auth_header(stranger))
    assert r.status_code == 404

    # owner 归档
    r = await client.put(f"/problems/{p['id']}/archive", json={"archived": True},
                         headers=await auth_header(normal_user))
    assert r.status_code == 200, r.text
    assert r.json()["archived"] is True

    # 刷题视角（即使 is_public 也不显示）、管理视角默认都排除归档题
    r = await client.get("/problems", headers=await auth_header(normal_user))
    assert p["id"] not in {int(x["id"]) for x in r.json()}
    r = await client.get("/problems?mine=1", headers=await auth_header(normal_user))
    assert p["id"] not in {int(x["id"]) for x in r.json()}

    # mine=1&archived=1：只看归档题
    r = await client.get("/problems?mine=1&archived=1", headers=await auth_header(normal_user))
    assert int(p["id"]) in {int(x["id"]) for x in r.json()}

    # 详情仍可访问（已有引用不失效）
    r = await client.get(f"/problems/{p['id']}", headers=await auth_header(normal_user))
    assert r.status_code == 200

    # 归档题不可提交
    r = await client.post("/submissions", json={
        "problem_id": p["id"], "language": "python3.12", "code": "print(1)"},
        headers=await auth_header(normal_user))
    assert r.status_code == 400
    assert "归档" in r.json()["detail"]

    # 恢复后：列表回归、可提交
    r = await client.put(f"/problems/{p['id']}/archive", json={"archived": False},
                         headers=await auth_header(normal_user))
    assert r.json()["archived"] is False
    r = await client.get("/problems?mine=1", headers=await auth_header(normal_user))
    assert int(p["id"]) in {int(x["id"]) for x in r.json()}


async def test_archive_hides_from_tag_cloud(client, normal_user, gateway):
    """标签云只统计未归档的公开题"""
    # 两道公开题打上同一归档测试标签（标签名唯一，不受其他测试干扰）
    p1 = await _make_public_problem(client, normal_user, title="标签归档题", tags=["归档测试标"])
    p2 = await _make_public_problem(client, normal_user, title="标签正常题", tags=["归档测试标"])
    r = await client.get("/problems/tags")
    counter = {x["tag"]: x["count"] for x in r.json()["items"]}
    assert counter["归档测试标"] == 2

    # 归档其一：计数减一
    await client.put(f"/problems/{p1['id']}/archive", json={"archived": True},
                     headers=await auth_header(normal_user))
    r = await client.get("/problems/tags")
    counter = {x["tag"]: x["count"] for x in r.json()["items"]}
    assert counter["归档测试标"] == 1
