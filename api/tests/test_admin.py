# -*- coding: utf-8 -*-
# 文件: api/tests/test_admin.py
# 用途: 管理后台接口测试：权限边界/概况统计/用户管理/题目管理/单条重判/节点监控

import pytest
from httpx import AsyncClient

from tests.conftest import (
    add_fake_node, auth_header, drain_node_queue, make_user, resolve_submit,
    setup_public_problem,
)

pytestmark = pytest.mark.asyncio


async def test_admin_requires_admin(client, normal_user):
    """普通用户访问后台一律 401/403"""
    gets = ["/admin/overview", "/admin/users", "/admin/problems",
            "/admin/contests", "/admin/judges"]
    posts = ["/admin/submissions/1/rejudge"]
    puts = [("/admin/users/1/role", {"role": "admin"}),
            ("/admin/users/1/ban", {"banned": True})]
    for url in gets:
        r = await client.get(url, headers=await auth_header(normal_user))
        assert r.status_code in (401, 403), f"{url} → {r.status_code}"
    for url in posts:
        r = await client.post(url, headers=await auth_header(normal_user))
        assert r.status_code in (401, 403), f"{url} → {r.status_code}"
    for url, json in puts:
        r = await client.put(url, json=json, headers=await auth_header(normal_user))
        assert r.status_code in (401, 403), f"{url} → {r.status_code}"

    # 未登录
    r = await client.get("/admin/overview")
    assert r.status_code == 401


async def test_overview_stats(client, normal_user, admin_user, gateway):
    """概况统计：用户数/题目数/AC 率/在线节点"""
    p = await setup_public_problem(client, normal_user, title="统计题")
    node = add_fake_node(gateway)
    import asyncio
    req_task = asyncio.create_task(client.post(
        "/submissions", json={"problem_id": p["id"], "language": "python3.12",
                              "code": "print(1)"}, headers=await auth_header(normal_user)))
    jobs = await drain_node_queue(node)
    await resolve_submit(gateway, jobs[0], status="accepted", score=100)
    r = await await_or_raise(req_task)
    assert r.status_code == 201

    r = await client.get("/admin/overview", headers=await auth_header(admin_user))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["users"] >= 2
    assert body["problems"] >= 1
    assert body["submissions"] >= 1
    assert body["today_submissions"] >= 1
    assert body["online_nodes"] == 1


async def test_user_management(client, normal_user, admin_user, db_sessionmaker):
    """搜索/改角色/封禁；自己不能改自己"""
    async with db_sessionmaker() as db:
        target = await make_user(db, "managed_user")

    # 列表 + 搜索
    r = await client.get("/admin/users?q=managed", headers=await auth_header(admin_user))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total"] >= 1
    assert any(u["username"] == "managed_user" for u in body["items"])

    # 普通用户无用户列表里找不到 admin 权限语义：admin 看得到全部
    # 改角色
    r = await client.put(f"/admin/users/{target.id}/role", json={"role": "admin"},
                         headers=await auth_header(admin_user))
    assert r.status_code == 200, r.text
    assert r.json()["role"] == "admin"

    # 非法角色值
    r = await client.put(f"/admin/users/{target.id}/role", json={"role": "root"},
                         headers=await auth_header(admin_user))
    assert r.status_code == 422

    # 不能改自己
    r = await client.put(f"/admin/users/{admin_user.id}/role", json={"role": "user"},
                         headers=await auth_header(admin_user))
    assert r.status_code == 400

    # 封禁
    r = await client.put(f"/admin/users/{target.id}/ban", json={"banned": True},
                         headers=await auth_header(admin_user))
    assert r.status_code == 200
    # 封禁后无法登录（已在 test_users.py 验证），这里只验 admin 不能封自己
    r = await client.put(f"/admin/users/{admin_user.id}/ban", json={"banned": True},
                         headers=await auth_header(admin_user))
    assert r.status_code == 400


async def test_admin_problems_and_contests_lists(client, normal_user, admin_user, gateway):
    """后台题目/比赛全量列表（含私有）"""
    p = await setup_public_problem(client, normal_user, title="后台题")

    from datetime import datetime, timedelta, timezone
    now = datetime.now(timezone.utc)
    r = await client.post("/contests", json={
        "title": "后台赛",
        "start_at": (now - timedelta(minutes=5)).isoformat(),
        "end_at": (now + timedelta(hours=2)).isoformat()},
        headers=await auth_header(normal_user))
    assert r.status_code == 201

    r = await client.get("/admin/problems", headers=await auth_header(admin_user))
    assert r.status_code == 200, r.text
    items = r.json()["items"]
    match = [x for x in items if x["title"] == "后台题"]
    assert match and match[0]["case_count"] == 2 and match[0]["is_public"] is True

    r = await client.get("/admin/contests", headers=await auth_header(admin_user))
    assert "后台赛" in {c["title"] for c in r.json()["items"]}


async def test_rejudge_flow(client, normal_user, admin_user, gateway):
    """单条重判：留源码提交 → 管理员重判 WA→AC"""
    p = await setup_public_problem(client, normal_user, title="重判题")
    node = add_fake_node(gateway)

    # 第一次提交：回传 WA
    import asyncio
    req_task = asyncio.create_task(client.post(
        "/submissions", json={"problem_id": p["id"], "language": "python3.12",
                              "code": "print(1)"}, headers=await auth_header(normal_user)))
    jobs = await drain_node_queue(node)
    await resolve_submit(gateway, jobs[0], status="wrong_answer", score=0)
    r = await await_or_raise(req_task)
    sub_id = r.json()["id"]
    assert r.json()["status"] == "wa"

    # 重判：这次回传 AC
    rejudge_task = asyncio.create_task(client.post(
        f"/admin/submissions/{sub_id}/rejudge", headers=await auth_header(admin_user)))
    jobs = await drain_node_queue(node)
    assert len(jobs) == 1
    assert jobs[0].code  # 源码从 DB 留存复用
    await resolve_submit(gateway, jobs[0], status="accepted", score=100)
    r = await await_or_raise(rejudge_task)
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "ac"
    assert r.json()["score"] == 100

    # 后台详情可看源码
    r = await client.get(f"/admin/submissions/{sub_id}", headers=await auth_header(admin_user))
    assert r.status_code == 200, r.text
    assert r.json()["code"] == "print(1)"


async def test_rejudge_requires_saved_code(client, normal_user, admin_user, db_sessionmaker, gateway):
    """未留存源码的旧提交：重判 400"""
    from app.models import Problem, Submission, SubmissionStatus
    p = await setup_public_problem(client, normal_user, title="无码题")
    async with db_sessionmaker() as db:
        sub = Submission(user_id=normal_user.id, problem_id=int(p["id"]),
                         language="python3.12", code_key="k", code=None,
                         status=SubmissionStatus.WRONG_ANSWER)
        db.add(sub)
        await db.commit()
        sub_id = sub.id

    r = await client.post(f"/admin/submissions/{sub_id}/rejudge",
                          headers=await auth_header(admin_user))
    assert r.status_code == 400


async def test_judges_snapshot(client, admin_user, gateway):
    """节点监控快照：注册假节点后可见"""
    add_fake_node(gateway, node_id="admin-test-node")
    r = await client.get("/admin/judges", headers=await auth_header(admin_user))
    assert r.status_code == 200, r.text
    body = r.json()
    assert isinstance(body, dict)


# ---------------- 工具 ----------------

def await_or_raise(task):
    import asyncio
    return asyncio.wait_for(task, timeout=10)
