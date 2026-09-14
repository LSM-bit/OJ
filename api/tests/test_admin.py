# -*- coding: utf-8 -*-
# 文件: api/tests/test_admin.py
# 用途: 管理后台接口测试：权限边界/概况统计/用户管理/题目管理/标签管理/单条重判/节点监控

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


async def test_admin_tag_manage(client, normal_user, admin_user):
    """标签管理：列表（含使用题数）/重命名同步题目 tags/删除移除题目 tags/重名 400/权限"""
    # 建 3 个标签实例，其中两个挂在题目上
    async def _mk(name: str) -> dict:
        r = await client.post("/problems/tags", json={"name": name},
                              headers=await auth_header(normal_user))
        assert r.status_code == 201, r.text
        return r.json()
    t_memo = await _mk("后台动态规划")
    t_greedy = await _mk("后台贪心")
    orphan = await _mk("孤儿标签")

    # 后台新建：成功 / 重名 400
    r = await client.post("/admin/tags", json={"name": "后台新建标签"},
                          headers=await auth_header(admin_user))
    assert r.status_code == 201, r.text
    assert r.json()["name"] == "后台新建标签"
    assert r.json()["problem_count"] == 0
    r = await client.post("/admin/tags", json={"name": " 后台新建标签 "},
                          headers=await auth_header(admin_user))
    assert r.status_code == 400
    r = await client.post("/admin/tags", json={"name": ""},
                          headers=await auth_header(admin_user))
    assert r.status_code == 422

    # 题目挂上两个标签（直接建草稿即可，无需发布）
    r = await client.post("/problems", json={"title": "标签管理题", "description": "d",
                                             "tags": [t_memo["name"], t_greedy["name"]]},
                          headers=await auth_header(normal_user))
    assert r.status_code == 201, r.text

    # 列表：使用题数 + 搜索
    r = await client.get("/admin/tags", headers=await auth_header(admin_user))
    assert r.status_code == 200, r.text
    by_name = {x["name"]: x for x in r.json()["items"]}
    assert by_name[t_memo["name"]]["problem_count"] == 1
    assert by_name[orphan["name"]]["problem_count"] == 0

    r = await client.get("/admin/tags?q=后台动态", headers=await auth_header(admin_user))
    names = {x["name"] for x in r.json()["items"]}
    assert t_memo["name"] in names and t_greedy["name"] not in names

    # 普通用户 403
    r = await client.get("/admin/tags", headers=await auth_header(normal_user))
    assert r.status_code in (401, 403)

    # 重命名：题目 tags 里的旧名同步替换
    new_name = "后台DP"
    r = await client.put(f"/admin/tags/{t_memo['id']}", json={"name": new_name},
                         headers=await auth_header(admin_user))
    assert r.status_code == 200, r.text
    assert r.json()["touched"] == 1

    # 题目 tags 里的旧名已同步替换（mine=1 出题视角可看草稿）
    r = await client.get("/problems?mine=1", headers=await auth_header(normal_user))
    assert r.status_code == 200, r.text
    p = [x for x in r.json() if x["title"] == "标签管理题"][0]
    assert new_name in p["tags"] and t_memo["name"] not in p["tags"]
    assert t_greedy["name"] in p["tags"]

    # 重命名成已存在的名字 → 400
    r = await client.put(f"/admin/tags/{t_greedy['id']}", json={"name": new_name},
                         headers=await auth_header(admin_user))
    assert r.status_code == 400

    # 删除：题目 tags 中移除该名，孤儿标签也可删
    r = await client.delete(f"/admin/tags/{t_greedy['id']}",
                            headers=await auth_header(admin_user))
    assert r.status_code == 200, r.text
    assert r.json()["touched"] == 1
    r = await client.delete(f"/admin/tags/{orphan['id']}",
                            headers=await auth_header(admin_user))
    assert r.status_code == 200
    assert r.json()["touched"] == 0

    r = await client.get("/problems?mine=1", headers=await auth_header(normal_user))
    p = [x for x in r.json() if x["title"] == "标签管理题"][0]
    assert new_name in p["tags"] and t_greedy["name"] not in p["tags"]

    # 删除后实例已不存在（搜索不到）
    r = await client.get("/problems/tags/search?q=后台贪心")
    assert r.json() == []

    # 后台新建的标签对前台弹窗搜索可见
    r = await client.get("/problems/tags/search?q=后台新建标签")
    assert [x["name"] for x in r.json()] == ["后台新建标签"]


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
