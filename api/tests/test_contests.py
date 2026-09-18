"""比赛模块接口测试：创建/报名/比赛内提交/榜单（判题结果由假节点编排）"""

import asyncio
import io
import json
import zipfile
from datetime import datetime, timedelta, timezone

import pytest
from httpx import AsyncClient

from tests.conftest import (
    add_fake_node, auth_header, drain_node_queue, make_user, resolve_submit,
)

pytestmark = pytest.mark.asyncio

AC_CODE = "s=input().split()\nprint(int(s[0])+int(s[1]))\n"


def _time_window(start_min=-5, duration=120) -> dict:
    now = datetime.now(timezone.utc)
    return {"start_at": (now + timedelta(minutes=start_min)).isoformat(),
            "end_at": (now + timedelta(minutes=start_min + duration)).isoformat()}


async def _setup_problem(client, user, title="A+B") -> dict:
    """建公开题（走三步出题），需要 gateway fixture"""
    from tests.conftest import setup_public_problem
    return await setup_public_problem(client, user, title=title,
                                      cases={"tc0": ("1 2", "3")})


async def test_create_contest_requires_auth(client):
    r = await client.post("/contests", json={"title": "t", **_time_window()})
    assert r.status_code == 401


async def test_create_contest_and_detail(client, normal_user, gateway):
    p = await _setup_problem(client, normal_user)
    r = await client.post("/contests", json={
        "title": "测试比赛", "rule": "acm", "problem_ids": [p["id"]],
        "board_freeze_minutes": 30, **_time_window()},
        headers=await auth_header(normal_user))
    assert r.status_code == 201, r.text
    c = r.json()
    assert c["rule"] == "acm"
    assert c["phase"] == "running"  # start=-5min

    r = await client.get(f"/contests/{c['id']}")
    assert r.status_code == 200
    detail = r.json()
    assert len(detail["problems"]) == 1
    assert detail["problems"][0]["alias"] == "A"
    assert detail["problems"][0]["visible"] is True  # 公开题


async def test_create_contest_invalid_time(client, normal_user):
    now = datetime.now(timezone.utc)
    r = await client.post("/contests", json={
        "title": "t",
        "start_at": now.isoformat(), "end_at": (now - timedelta(minutes=1)).isoformat()},
        headers=await auth_header(normal_user))
    assert r.status_code == 400


async def test_create_contest_unknown_problem(client, normal_user):
    r = await client.post("/contests", json={
        "title": "t", "problem_ids": [999999], **_time_window()},
        headers=await auth_header(normal_user))
    assert r.status_code == 400


async def test_register_and_duplicate(client, normal_user, db_sessionmaker):
    async with db_sessionmaker() as db:
        other = await make_user(db, "reg_user")
    r = await client.post("/contests", json={"title": "t", **_time_window()},
                          headers=await auth_header(normal_user))
    cid = r.json()["id"]

    r = await client.post(f"/contests/{cid}/register", headers=await auth_header(other))
    assert r.status_code == 201
    assert r.json()["ok"] is True

    # 重复报名：幂等返回 already
    r = await client.post(f"/contests/{cid}/register", headers=await auth_header(other))
    assert r.status_code == 201
    assert r.json().get("already") is True


async def test_register_requires_auth(client, normal_user):
    r = await client.post("/contests", json={"title": "t", **_time_window()},
                          headers=await auth_header(normal_user))
    cid = r.json()["id"]
    r = await client.post(f"/contests/{cid}/register")
    assert r.status_code == 401


async def test_contest_submit_not_registered(client, normal_user, db_sessionmaker, gateway):
    """未报名 → 403"""
    p = await _setup_problem(client, normal_user)
    r = await client.post("/contests", json={
        "title": "t", "problem_ids": [p["id"]], **_time_window()},
        headers=await auth_header(normal_user))
    cid = r.json()["id"]

    async with db_sessionmaker() as db:
        stranger = await make_user(db, "no_reg")
    r = await client.post(f"/contests/{cid}/problems/A/submit",
                          json={"language": "python3.12", "code": AC_CODE},
                          headers=await auth_header(stranger))
    assert r.status_code == 403


async def test_contest_submit_not_running(client, normal_user, gateway):
    """未开始的比赛不能提交"""
    p = await _setup_problem(client, normal_user)
    r = await client.post("/contests", json={
        "title": "t", "problem_ids": [p["id"]], **_time_window(start_min=30)},
        headers=await auth_header(normal_user))
    cid = r.json()["id"]
    r = await client.post(f"/contests/{cid}/problems/A/submit",
                          json={"language": "python3.12", "code": AC_CODE},
                          headers=await auth_header(normal_user))
    assert r.status_code == 400


async def test_contest_submit_flow_and_standings(client, normal_user, gateway):
    """完整链路：建赛→报名→比赛内提交（假节点 AC）→榜单出现解题记录"""
    p = await _setup_problem(client, normal_user)
    r = await client.post("/contests", json={
        "title": "t", "rule": "acm", "problem_ids": [p["id"]], **_time_window()},
        headers=await auth_header(normal_user))
    cid = r.json()["id"]

    r = await client.post(f"/contests/{cid}/register", headers=await auth_header(normal_user))
    assert r.status_code == 201

    node = add_fake_node(gateway)
    req_task = asyncio.create_task(client.post(
        f"/contests/{cid}/problems/A/submit",
        json={"language": "python3.12", "code": AC_CODE},
        headers=await auth_header(normal_user)))
    jobs = await drain_node_queue(node)
    assert len(jobs) == 1
    # ACM 赛制 stop_on_failure=True（队列里是 job dict）
    assert jobs[0]["stop_on_failure"] is True
    assert jobs[0]["problem_id"] == str(p["id"])
    await resolve_submit(gateway, jobs[0], status="accepted", score=100)

    r = await await_or_raise(req_task)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["status"] == "ac"
    # 比赛进行中不透露测试点细节（防打表）
    assert body["detail"] == []

    # 榜单
    r = await client.get(f"/contests/{cid}/standings")
    assert r.status_code == 200
    rows = r.json()["rows"]
    assert len(rows) == 1
    row = rows[0]
    assert row["username"] == "alice" or row["user_id"] == normal_user.id
    assert row["solved"] == 1
    assert row["cells"][0]["solved"] is True
    assert 0 <= row["cells"][0]["solve_time"] <= 10  # 刚开赛几分钟内


async def test_contest_submit_unknown_alias(client, normal_user, gateway):
    p = await _setup_problem(client, normal_user)
    r = await client.post("/contests", json={
        "title": "t", "problem_ids": [p["id"]], **_time_window()},
        headers=await auth_header(normal_user))
    cid = r.json()["id"]
    await client.post(f"/contests/{cid}/register", headers=await auth_header(normal_user))
    r = await client.post(f"/contests/{cid}/problems/Z/submit",
                          json={"language": "python3.12", "code": AC_CODE},
                          headers=await auth_header(normal_user))
    assert r.status_code == 404


async def test_contest_list_visibility(client, normal_user, db_sessionmaker, gateway):
    """私有比赛对陌生人不可见"""
    p = await _setup_problem(client, normal_user)
    r = await client.post("/contests", json={
        "title": "private-contest", "is_public": False, "problem_ids": [p["id"]],
        **_time_window()},
        headers=await auth_header(normal_user))
    assert r.status_code == 201
    cid = r.json()["id"]

    async with db_sessionmaker() as db:
        stranger = await make_user(db, " outsider")
    r = await client.get("/contests", headers=await auth_header(stranger))
    titles = {x["title"] for x in r.json()}
    assert "private-contest" not in titles

    r = await client.get(f"/contests/{cid}", headers=await auth_header(stranger))
    assert r.status_code == 404  # 防枚举

    # owner 可见
    r = await client.get("/contests", headers=await auth_header(normal_user))
    assert "private-contest" in {x["title"] for x in r.json()}


async def test_cannot_add_others_private_problem_to_contest(client, normal_user, db_sessionmaker):
    """他人私有题不能加进比赛（防借比赛泄露私有题）"""
    async with db_sessionmaker() as db:
        owner = await make_user(db, "ct_priv_owner")
    r = await client.post("/problems", json={"title": "比赛私题", "description": "d"},
                          headers=await auth_header(owner))
    assert r.status_code == 201
    priv = r.json()

    r = await client.post("/contests", json={
        "title": "t", "problem_ids": [priv["id"]], **_time_window()},
        headers=await auth_header(normal_user))
    assert r.status_code == 403, r.text
    assert "私有" in r.json()["detail"]


async def test_frozen_board_hides_new_submissions(client, normal_user, db_sessionmaker, gateway):
    """封榜后 AC 的提交：榜单不即时涨分（frozen），detail 仍为 []"""
    from tests.conftest import setup_public_problem

    p = await setup_public_problem(client, normal_user, title="封榜题")
    r = await client.post("/contests", json={
        "title": "t", "rule": "acm", "problem_ids": [p["id"]],
        "board_freeze_minutes": 30, **_time_window()},
        headers=await auth_header(normal_user))
    assert r.status_code == 201, r.text
    cid = r.json()["id"]
    await client.post(f"/contests/{cid}/register", headers=await auth_header(normal_user))

    node = add_fake_node(gateway)
    req_task = asyncio.create_task(client.post(
        f"/contests/{cid}/problems/A/submit",
        json={"language": "python3.12", "code": AC_CODE},
        headers=await auth_header(normal_user)))
    jobs = await drain_node_queue(node)
    await resolve_submit(gateway, jobs[0], status="accepted", score=100)
    r = await await_or_raise(req_task)
    assert r.status_code == 201, r.text

    # 开赛 5 分钟 + 封榜 30 分钟 → 未到封榜线，榜单应正常显示解题
    r = await client.get(f"/contests/{cid}/standings")
    rows = r.json()["rows"]
    assert len(rows) == 1
    assert rows[0]["solved"] == 1


async def test_contest_submission_detail_permission(client, normal_user, db_sessionmaker, gateway):
    """提交详情权限：本人/比赛管理者可见；陌生人 404 防枚举；未登录 401"""
    p = await _setup_problem(client, normal_user)
    r = await client.post("/contests", json={
        "title": "t", "problem_ids": [p["id"]], **_time_window()},
        headers=await auth_header(normal_user))
    cid = r.json()["id"]
    await client.post(f"/contests/{cid}/register", headers=await auth_header(normal_user))
    body = await _submit_in_contest(client, cid, normal_user, gateway)
    sid = body["id"]

    # 本人（兼比赛创建者）：源码 + 测试点明细均可见
    r = await client.get(f"/contests/{cid}/submissions/{sid}",
                         headers=await auth_header(normal_user))
    assert r.status_code == 200
    d = r.json()
    assert d["code"] == AC_CODE
    assert len(d["detail"]) == 1  # 假节点回传的单测试点

    # 陌生人：404（与不存在同响应，防枚举）
    async with db_sessionmaker() as db:
        stranger = await make_user(db, "sub_detail_stranger")
    r = await client.get(f"/contests/{cid}/submissions/{sid}",
                         headers=await auth_header(stranger))
    assert r.status_code == 404

    # 未登录：401
    r = await client.get(f"/contests/{cid}/submissions/{sid}")
    assert r.status_code == 401


async def test_contest_submission_detail_anti_lookup(client, normal_user, db_sessionmaker, gateway):
    """防打表：进行中本人只见源码无明细；管理者随时可见；结束后本人可见"""
    p = await _setup_problem(client, normal_user)
    r = await client.post("/contests", json={
        "title": "t", "problem_ids": [p["id"]], **_time_window()},
        headers=await auth_header(normal_user))
    cid = r.json()["id"]

    async with db_sessionmaker() as db:
        player = await make_user(db, "sub_detail_player")
    await client.post(f"/contests/{cid}/register", headers=await auth_header(player))
    body = await _submit_in_contest(client, cid, player, gateway,
                                    status="wrong_answer", score=0)
    sid = body["id"]

    # 进行中：本人只有源码，测试点明细隐藏
    r = await client.get(f"/contests/{cid}/submissions/{sid}",
                         headers=await auth_header(player))
    assert r.status_code == 200
    d = r.json()
    assert d["code"] == AC_CODE
    assert d["detail"] == []

    # 管理者（比赛创建者）：随时可见明细
    r = await client.get(f"/contests/{cid}/submissions/{sid}",
                         headers=await auth_header(normal_user))
    assert len(r.json()["detail"]) == 1

    # 结束后（创建者把结束时间改到过去）：本人可见明细
    past = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
    r = await client.patch(f"/contests/{cid}", json={"end_at": past},
                           headers=await auth_header(normal_user))
    assert r.status_code == 200, r.text
    r = await client.get(f"/contests/{cid}/submissions/{sid}",
                         headers=await auth_header(player))
    assert len(r.json()["detail"]) == 1


async def test_contest_submission_detail_ce_error_visible(client, normal_user, db_sessionmaker, gateway):
    """CE：编译错误信息不含测试数据，进行中对本人（非管理者）也可见（测试点明细仍隐藏）"""
    p = await _setup_problem(client, normal_user)
    r = await client.post("/contests", json={
        "title": "t", "problem_ids": [p["id"]], **_time_window()},
        headers=await auth_header(normal_user))
    cid = r.json()["id"]

    async with db_sessionmaker() as db:
        player = await make_user(db, "sub_detail_ce")
    await client.post(f"/contests/{cid}/register", headers=await auth_header(player))
    body = await _submit_in_contest(client, cid, player, gateway,
                                    status="compile_error", score=0,
                                    error_message="SyntaxError: invalid syntax")
    sid = body["id"]

    r = await client.get(f"/contests/{cid}/submissions/{sid}",
                         headers=await auth_header(player))
    assert r.status_code == 200
    d = r.json()
    assert "SyntaxError" in d["error_message"]
    assert d["detail"] == []  # 测试点明细进行中仍隐藏
    assert d["code"] == AC_CODE


async def test_archived_contest_no_edit_but_submit_and_vp(client, normal_user, db_sessionmaker, gateway):
    """结束满 24h 自动归档：不能再编辑；仍可提交练习、可创建重现赛(VP)"""
    p = await _setup_problem(client, normal_user)
    # start 1501min 前 + 60min 时长 → 结束已满 24h 又 1 分钟
    r = await client.post("/contests", json={
        "title": "old-contest", "problem_ids": [p["id"]],
        **_time_window(start_min=-1501, duration=60)},
        headers=await auth_header(normal_user))
    cid = r.json()["id"]
    assert r.json()["archived"] is True

    # 详情与列表都携带派生的 archived 标记（前端按它分「未结束/已结束(归档)」两类）
    r = await client.get(f"/contests/{cid}")
    assert r.json()["archived"] is True
    r = await client.get("/contests")
    assert any(x["id"] == cid and x["archived"] for x in r.json())

    # 归档后不能再编辑比赛信息
    future = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()
    r = await client.patch(f"/contests/{cid}", json={"end_at": future},
                           headers=await auth_header(normal_user))
    assert r.status_code == 400 and "归档" in r.json()["detail"]

    # 仍可提交：未报名的旁观者也能对归档比赛做练习提交
    async with db_sessionmaker() as db:
        visitor = await make_user(db, "archived_visitor")
    body = await _submit_in_contest(client, cid, visitor, gateway)
    assert body["status"] == "ac"

    # 可创建重现赛：默认私有、复制题目与别名、自动报名、立即开始
    r = await client.post(f"/contests/{cid}/vp", json={},
                          headers=await auth_header(visitor))
    assert r.status_code == 201, r.text
    vp = r.json()
    assert vp["vp_of"] == cid
    assert vp["is_public"] is False and vp["archived"] is False
    assert vp["phase"] == "running" and vp["board_freeze_minutes"] == 0
    assert vp["problems"] == 1 and "重现赛" in vp["title"]
    r = await client.get(f"/contests/{vp['id']}", headers=await auth_header(visitor))
    assert r.json()["problems"][0]["alias"] == "A"
    rows = (await client.get(f"/contests/{vp['id']}/standings",
                             headers=await auth_header(visitor))).json()["rows"]
    assert [x["username"] for x in rows] == ["archived_visitor"]  # 创建者已自动报名

    # VP 时间窗非法同样被拒
    r = await client.post(f"/contests/{cid}/vp",
                          json={"start_at": future, "end_at": future},
                          headers=await auth_header(visitor))
    assert r.status_code == 400


async def test_ended_not_archived_still_editable(client, normal_user, gateway):
    """结束未满 24h 不算归档：仍可编辑（改时间也会顺延归档时刻，派生设计）"""
    p = await _setup_problem(client, normal_user)
    r = await client.post("/contests", json={
        "title": "t", "problem_ids": [p["id"]], **_time_window(start_min=-180, duration=120)},
        headers=await auth_header(normal_user))
    body = r.json()
    assert body["phase"] == "ended" and body["archived"] is False
    future = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()
    r = await client.patch(f"/contests/{body['id']}", json={"end_at": future},
                           headers=await auth_header(normal_user))
    assert r.status_code == 200


# ---------------- 工具 ----------------

def await_or_raise(task):
    return asyncio.wait_for(task, timeout=10)


async def _submit_in_contest(client, cid: int, user, gateway, *,
                             status: str = "accepted", score: int = 100,
                             error_message: str = "") -> dict:
    """在比赛内提交 A 题并用假节点回传指定结果，返回提交响应 JSON"""
    node = add_fake_node(gateway)  # 每次新节点，避免与其他用例的队列混用
    node_id = node.node_id
    req_task = asyncio.create_task(client.post(
        f"/contests/{cid}/problems/A/submit",
        json={"language": "python3.12", "code": AC_CODE},
        headers=await auth_header(user)))
    jobs = await drain_node_queue(node)
    if not jobs:
        # 调度轮询可能选中早前的假节点（容量未释放），清空其队列重试一次
        older = [n for nid, n in gateway.nodes.items() if nid != node_id]
        for n in older:
            jobs += await drain_node_queue(n)
    assert jobs, "任务未被任何假节点接收"
    await resolve_submit(gateway, jobs[0], status=status, score=score,
                         error_message=error_message)
    r = await await_or_raise(req_task)
    assert r.status_code == 201, r.text
    return r.json()
