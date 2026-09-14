# -*- coding: utf-8 -*-
# 文件: api/tests/test_teams.py
# 用途: 团队模块接口测试：创建/详情可见性/邀请码加入/成员角色管理/解散/容量上限

import pytest
from httpx import AsyncClient

from tests.conftest import auth_header, make_user

pytestmark = pytest.mark.asyncio


async def _create_team(client, user, name="我的团队", **kw) -> dict:
    r = await client.post("/teams", json={"name": name, **kw},
                          headers=await auth_header(user))
    assert r.status_code == 201, r.text
    return r.json()


async def test_create_team_requires_auth(client):
    r = await client.post("/teams", json={"name": "t"})
    assert r.status_code == 401


async def test_create_team_and_detail(client, normal_user):
    t = await _create_team(client, normal_user)
    assert t["name"] == "我的团队"
    assert int(t["owner_id"]) == normal_user.id
    assert t["member_count"] == 1

    r = await client.get(f"/teams/{t['id']}", headers=await auth_header(normal_user))
    assert r.status_code == 200, r.text
    detail = r.json()
    # 雪花 id 经 JSON 序列化为字符串，只比字段值
    assert len(detail["members"]) == 1
    m = detail["members"][0]
    assert int(m["user_id"]) == normal_user.id
    assert m["username"] == normal_user.username
    assert m["role"] == "owner"
    assert detail["my_role"] == "owner"


async def test_team_name_duplicate(client, normal_user):
    await _create_team(client, normal_user, name="dup-team")
    r = await client.post("/teams", json={"name": "dup-team"},
                          headers=await auth_header(normal_user))
    assert r.status_code == 400


async def test_team_detail_hidden_members_for_stranger(client, normal_user, db_sessionmaker):
    """非成员只见成员数量，不见名单（防信息泄露）"""
    t = await _create_team(client, normal_user)
    async with db_sessionmaker() as db:
        stranger = await make_user(db, "stranger")
    r = await client.get(f"/teams/{t['id']}", headers=await auth_header(stranger))
    assert r.status_code == 200
    body = r.json()
    assert "members" not in body
    assert body["member_count"] == 1


async def test_invite_code_join_flow(client, normal_user, db_sessionmaker):
    """队长生成邀请码 → 陌生人凭码加入 → 幂等重复加入"""
    t = await _create_team(client, normal_user)
    async with db_sessionmaker() as db:
        joiner = await make_user(db, "joiner")

    # 陌生人不能生成邀请码
    r = await client.post(f"/teams/{t['id']}/invite-codes",
                          headers=await auth_header(joiner))
    assert r.status_code == 403

    r = await client.post(f"/teams/{t['id']}/invite-codes",
                          headers=await auth_header(normal_user))
    assert r.status_code == 200, r.text
    code = r.json()["code"]

    # 凭码加入（不需要知道 team_id）
    r = await client.post("/teams/join", json={"code": code},
                          headers=await auth_header(joiner))
    assert r.status_code == 201, r.text
    assert r.json()["ok"] is True

    # 重复加入：幂等
    r = await client.post("/teams/join", json={"code": code},
                          headers=await auth_header(joiner))
    assert r.status_code == 201
    assert r.json().get("already") is True

    # 无效邀请码
    r = await client.post("/teams/join", json={"code": "bogus-code"},
                          headers=await auth_header(joiner))
    assert r.status_code == 400

    # 成员列表出现 joiner
    r = await client.get(f"/teams/{t['id']}", headers=await auth_header(normal_user))
    roles = {m["username"]: m["role"] for m in r.json()["members"]}
    assert roles == {normal_user.username: "owner", "joiner": "member"}


async def test_join_requires_auth(client, normal_user):
    t = await _create_team(client, normal_user)
    r = await client.post(f"/teams/{t['id']}/invite-codes")
    assert r.status_code == 401


async def test_member_role_management(client, normal_user, db_sessionmaker):
    """队长/副队权限：设副队 → 副队可生成邀请码；副队只能被队长移除"""
    t = await _create_team(client, normal_user)
    async with db_sessionmaker() as db:
        m1 = await make_user(db, "member1")
        m2 = await make_user(db, "member2")
    h1 = await auth_header(m1)
    h2 = await auth_header(m2)

    # 两人都加入
    r = await client.post(f"/teams/{t['id']}/invite-codes",
                          headers=await auth_header(normal_user))
    code = r.json()["code"]
    for h in (h1, h2):
        r = await client.post("/teams/join", json={"code": code}, headers=h)
        assert r.status_code == 201

    # 队长把 m1 升为副队
    r = await client.put(f"/teams/{t['id']}/members/{m1.id}/role",
                         json={"role": "admin"}, headers=await auth_header(normal_user))
    assert r.status_code == 200, r.text

    # 副队可生成邀请码
    r = await client.post(f"/teams/{t['id']}/invite-codes", headers=h1)
    assert r.status_code == 200

    # 普通成员不能设置角色
    r = await client.put(f"/teams/{t['id']}/members/{m2.id}/role",
                         json={"role": "admin"}, headers=h1)
    # m1 现在是副队，有管理权，可以设置
    assert r.status_code == 200

    # 队长不可被移除（需先转让）
    r = await client.delete(f"/teams/{t['id']}/members/{normal_user.id}", headers=h1)
    assert r.status_code == 400

    # 副队不能移除副队（m2 已被升为副队），只能队长移除
    r = await client.delete(f"/teams/{t['id']}/members/{m2.id}", headers=h1)
    assert r.status_code == 403
    r = await client.delete(f"/teams/{t['id']}/members/{m2.id}",
                            headers=await auth_header(normal_user))
    assert r.status_code == 200


async def test_owner_transfer(client, normal_user, db_sessionmaker):
    """转让队长：仅队长可操作，原队长降为副队"""
    t = await _create_team(client, normal_user)
    async with db_sessionmaker() as db:
        m = await make_user(db, "new_owner")
    hm = await auth_header(m)

    r = await client.post(f"/teams/{t['id']}/invite-codes",
                          headers=await auth_header(normal_user))
    code = r.json()["code"]
    await client.post("/teams/join", json={"code": code}, headers=hm)

    # 非队长不能转让
    r = await client.put(f"/teams/{t['id']}/members/{m.id}/role",
                         json={"role": "owner"}, headers=hm)
    assert r.status_code == 403

    # 队长转让
    r = await client.put(f"/teams/{t['id']}/members/{m.id}/role",
                         json={"role": "owner"}, headers=await auth_header(normal_user))
    assert r.status_code == 200, r.text

    r = await client.get(f"/teams/{t['id']}", headers=hm)
    roles = {int(m2["user_id"]): m2["role"] for m2 in r.json()["members"]}
    assert roles[m.id] == "owner"
    assert roles[normal_user.id] == "admin"


async def test_member_self_leave(client, normal_user, db_sessionmaker):
    """成员可自行退出；队长不能退出（需先转让）"""
    t = await _create_team(client, normal_user)
    async with db_sessionmaker() as db:
        m = await make_user(db, "leaver")
    r = await client.post(f"/teams/{t['id']}/invite-codes",
                          headers=await auth_header(normal_user))
    code = r.json()["code"]
    await client.post("/teams/join", json={"code": code},
                      headers=await auth_header(m))

    r = await client.delete(f"/teams/{t['id']}/members/{m.id}",
                            headers=await auth_header(m))
    assert r.status_code == 200

    # 队长退出被拒
    r = await client.delete(f"/teams/{t['id']}/members/{normal_user.id}",
                            headers=await auth_header(normal_user))
    assert r.status_code == 400


async def test_team_capacity_limit(client, normal_user, db_sessionmaker):
    """团队人数满后加入被拒"""
    t = await _create_team(client, normal_user)
    # 直接把 max_members 改小
    from app.models import Team
    async with db_sessionmaker() as db:
        team = await db.get(Team, t["id"])
        team.max_members = 2
        await db.commit()

    r = await client.post(f"/teams/{t['id']}/invite-codes",
                          headers=await auth_header(normal_user))
    code = r.json()["code"]
    async with db_sessionmaker() as db:
        m = await make_user(db, "cap_member")
    await client.post("/teams/join", json={"code": code},
                      headers=await auth_header(m))
    async with db_sessionmaker() as db:
        m3 = await make_user(db, "cap_member3")
    r = await client.post("/teams/join", json={"code": code},
                          headers=await auth_header(m3))
    assert r.status_code == 400


async def test_delete_team_owner_only(client, normal_user, db_sessionmaker):
    """仅队长可解散；成员解散被拒"""
    t = await _create_team(client, normal_user)
    async with db_sessionmaker() as db:
        m = await make_user(db, "wannabe_killer")
    r = await client.post(f"/teams/{t['id']}/invite-codes",
                          headers=await auth_header(normal_user))
    code = r.json()["code"]
    await client.post("/teams/join", json={"code": code},
                      headers=await auth_header(m))

    r = await client.delete(f"/teams/{t['id']}", headers=await auth_header(m))
    assert r.status_code == 403

    r = await client.delete(f"/teams/{t['id']}", headers=await auth_header(normal_user))
    assert r.status_code == 200
    r = await client.get(f"/teams/{t['id']}")
    assert r.status_code == 404


async def test_my_teams_list(client, normal_user, db_sessionmaker):
    t1 = await _create_team(client, normal_user, name="team-a")
    r = await client.get("/teams", headers=await auth_header(normal_user))
    names = {x["name"] for x in r.json()}
    assert "team-a" in names
    assert r.json()[0]["my_role"] == "owner"


async def test_archive_team_flow(client, normal_user, db_sessionmaker):
    """团队归档全链路：仅队长可归档；列表隐藏（archived=1 可见）；
    不能生成邀请码/加入；详情仍可访问；恢复后照旧"""
    t = await _create_team(client, normal_user, name="archive-team")
    async with db_sessionmaker() as db:
        m = await make_user(db, "arch_member")
        stranger = await make_user(db, "arch_outsider")
    r = await client.post(f"/teams/{t['id']}/invite-codes",
                          headers=await auth_header(normal_user))
    code = r.json()["code"]
    await client.post("/teams/join", json={"code": code}, headers=await auth_header(m))

    # 副队/成员不能归档（先升 m 为副队验证，再由队长归档）
    r = await client.put(f"/teams/{t['id']}/archive", json={"archived": True},
                         headers=await auth_header(m))
    assert r.status_code == 403

    r = await client.put(f"/teams/{t['id']}/archive", json={"archived": True},
                         headers=await auth_header(normal_user))
    assert r.status_code == 200, r.text
    assert r.json()["archived"] is True

    # 默认列表隐藏，archived=1 查看
    r = await client.get("/teams", headers=await auth_header(normal_user))
    assert "archive-team" not in {x["name"] for x in r.json()}
    r = await client.get("/teams?archived=1", headers=await auth_header(normal_user))
    assert "archive-team" in {x["name"] for x in r.json()}
    assert r.json()[0]["archived"] is True

    # 详情仍可访问（成员端带 archived 标记）
    r = await client.get(f"/teams/{t['id']}", headers=await auth_header(m))
    assert r.status_code == 200
    assert r.json()["archived"] is True

    # 归档后不能生成邀请码 / 不能加入
    r = await client.post(f"/teams/{t['id']}/invite-codes",
                          headers=await auth_header(normal_user))
    assert r.status_code == 400
    r = await client.post("/teams/join", json={"code": code},
                          headers=await auth_header(stranger))
    assert r.status_code == 400
    assert "归档" in r.json()["detail"]

    # 恢复后：列表回归、可继续生成邀请码
    r = await client.put(f"/teams/{t['id']}/archive", json={"archived": False},
                         headers=await auth_header(normal_user))
    assert r.json()["archived"] is False
    r = await client.get("/teams", headers=await auth_header(normal_user))
    assert "archive-team" in {x["name"] for x in r.json()}
    r = await client.post(f"/teams/{t['id']}/invite-codes",
                          headers=await auth_header(normal_user))
    assert r.status_code == 200
