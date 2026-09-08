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
