# -*- coding: utf-8 -*-
# 文件: api/tests/test_playlists.py
# 用途: 题单模块接口测试：创建/可见性/加题权限/进度统计/团队归属

import pytest
from httpx import AsyncClient

from tests.conftest import auth_header, make_user, setup_public_problem

pytestmark = pytest.mark.asyncio


async def _create_playlist(client, user, title="基础题单", **kw) -> dict:
    r = await client.post("/playlists", json={"title": title, **kw},
                          headers=await auth_header(user))
    assert r.status_code == 201, r.text
    return r.json()


async def test_create_playlist_requires_auth(client):
    r = await client.post("/playlists", json={"title": "t"})
    assert r.status_code == 401


async def test_create_and_detail_progress(client, normal_user, db_sessionmaker, gateway):
    """创建题单 → 加公开题 → 详情带进度（AC 后 solved_problem_ids 出现）"""
    p = await setup_public_problem(client, normal_user, title="P1")
    pl = await _create_playlist(client, normal_user)

    r = await client.put(f"/playlists/{pl['id']}/problems",
                         json={"problem_ids": [p["id"]]},
                         headers=await auth_header(normal_user))
    assert r.status_code == 201, r.text
    assert r.json()["count"] == 1

    # 未提交时进度为空
    r = await client.get(f"/playlists/{pl['id']}", headers=await auth_header(normal_user))
    assert r.status_code == 200, r.text
    body = r.json()
    assert [it["title"] for it in body["problems"]] == ["P1"]
    assert body["solved_problem_ids"] == []

    # 模拟一条 AC 记录（不触发判题，直接落库）
    from app.models import Submission, SubmissionStatus
    async with db_sessionmaker() as db:
        db.add(Submission(user_id=normal_user.id, problem_id=p["id"],
                          language="python3.12", code_key="k",
                          status=SubmissionStatus.ACCEPTED, score=100))
        await db.commit()

    r = await client.get(f"/playlists/{pl['id']}", headers=await auth_header(normal_user))
    assert r.json()["solved_problem_ids"] == [p["id"]]


async def test_playlist_visibility(client, normal_user, db_sessionmaker):
    """私有题单：陌生人列表看不到、详情 404；owner 正常"""
    pl = await _create_playlist(client, normal_user, title="秘密题单", is_public=False)

    async with db_sessionmaker() as db:
        stranger = await make_user(db, "pl_stranger")

    r = await client.get("/playlists", headers=await auth_header(stranger))
    assert "秘密题单" not in {x["title"] for x in r.json()}

    r = await client.get(f"/playlists/{pl['id']}", headers=await auth_header(stranger))
    assert r.status_code == 404  # 防枚举

    r = await client.get("/playlists", headers=await auth_header(normal_user))
    assert "秘密题单" in {x["title"] for x in r.json()}


async def test_public_playlist_visible_to_all(client, normal_user, db_sessionmaker):
    """公开题单未登录也可见"""
    await _create_playlist(client, normal_user, title="公开题单", is_public=True)
    r = await client.get("/playlists")
    assert "公开题单" in {x["title"] for x in r.json()}


async def test_set_problems_requires_manage(client, normal_user, db_sessionmaker, gateway):
    """非管理权成员不能改题单题目"""
    p = await setup_public_problem(client, normal_user, title="P1")
    pl = await _create_playlist(client, normal_user, title="管理测试")
    async with db_sessionmaker() as db:
        other = await make_user(db, "pl_other")

    r = await client.put(f"/playlists/{pl['id']}/problems",
                         json={"problem_ids": [p["id"]]},
                         headers=await auth_header(other))
    assert r.status_code == 404  # 无权统一按"不存在"处理（防枚举）


async def test_cannot_add_others_private_problem(client, normal_user, db_sessionmaker, gateway):
    """他人私有题不能加进题单（防借题单泄露）"""
    async with db_sessionmaker() as db:
        owner = await make_user(db, "priv_owner")
    r = await client.post("/problems", json={"title": "私题", "description": "d"},
                          headers=await auth_header(owner))
    assert r.status_code == 201
    priv = r.json()

    pl = await _create_playlist(client, normal_user, title="偷题单")
    r = await client.put(f"/playlists/{pl['id']}/problems",
                         json={"problem_ids": [priv["id"]]},
                         headers=await auth_header(normal_user))
    assert r.status_code == 403, r.text


async def test_unknown_problem_rejected(client, normal_user):
    pl = await _create_playlist(client, normal_user, title="t")
    r = await client.put(f"/playlists/{pl['id']}/problems",
                         json={"problem_ids": [424242]},
                         headers=await auth_header(normal_user))
    assert r.status_code == 400


async def test_team_playlist_membership_visibility(client, normal_user, db_sessionmaker, gateway):
    """团队题单：成员可见，陌生人不可见；非管理权成员不能改"""
    # 建团队
    r = await client.post("/teams", json={"name": "pl-team"},
                          headers=await auth_header(normal_user))
    assert r.status_code == 201, r.text
    team_id = r.json()["id"]

    r = await client.post(f"/teams/{team_id}/invite-codes",
                          headers=await auth_header(normal_user))
    code = r.json()["code"]

    async with db_sessionmaker() as db:
        mate = await make_user(db, "teammate")
        stranger = await make_user(db, "no_team")
    r = await client.post("/teams/join", json={"code": code},
                          headers=await auth_header(mate))
    assert r.status_code == 201, r.text

    # 队长建团队题单
    pl = await _create_playlist(client, normal_user, title="团队题单",
                                owner_type="team", team_id=team_id)
    r = await client.get(f"/playlists/{pl['id']}", headers=await auth_header(mate))
    assert r.status_code == 200, r.text

    r = await client.get(f"/playlists/{pl['id']}", headers=await auth_header(stranger))
    assert r.status_code == 404

    # 普通成员没有管理权（无权统一 404 防枚举）
    r = await client.put(f"/playlists/{pl['id']}",
                         json={"title": "被篡改"},
                         headers=await auth_header(mate))
    assert r.status_code == 404


async def test_update_playlist_fields(client, normal_user):
    pl = await _create_playlist(client, normal_user, title="旧名", is_public=False)
    r = await client.put(f"/playlists/{pl['id']}",
                         json={"title": "新名", "is_public": True},
                         headers=await auth_header(normal_user))
    assert r.status_code == 200, r.text
    assert r.json()["title"] == "新名"
    assert r.json()["is_public"] is True


async def test_delete_playlist(client, normal_user, db_sessionmaker, gateway):
    """删除题单：仅管理者可删；删后列表/详情均不可见；题目本身不受影响"""
    from app.models import Problem

    p = await setup_public_problem(client, normal_user, title="题单里的题")
    pl = await _create_playlist(client, normal_user, title="待删除题单")
    r = await client.put(f"/playlists/{pl['id']}/problems",
                         json={"problem_ids": [p["id"]]},
                         headers=await auth_header(normal_user))
    assert r.status_code == 201, r.text

    # 陌生人删除 → 404 防枚举
    async with db_sessionmaker() as db:
        stranger = await make_user(db, "pl_del_stranger")
    r = await client.delete(f"/playlists/{pl['id']}", headers=await auth_header(stranger))
    assert r.status_code == 404

    # owner 删除
    r = await client.delete(f"/playlists/{pl['id']}", headers=await auth_header(normal_user))
    assert r.status_code == 200, r.text

    # 列表与详情都不在了
    r = await client.get("/playlists", headers=await auth_header(normal_user))
    assert "待删除题单" not in {x["title"] for x in r.json()}
    r = await client.get(f"/playlists/{pl['id']}", headers=await auth_header(normal_user))
    assert r.status_code == 404

    # 关联的题目本身不受影响
    async with db_sessionmaker() as db:
        assert await db.get(Problem, int(p["id"])) is not None
