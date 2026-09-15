# test_assistant.py - AI 助手路由测试（信息：api/tests/test_assistant.py）
# 用途：会话 CRUD 鉴权、/assistant/chat SSE 端到端（假助手节点流）、
#       比赛进行中禁用红线（参赛者 403 / 非参赛者放行 / ADMIN 豁免 / 赛后恢复）、
#       日配额 429、无节点 503、工具越权与禁读清单（solution_code 绝不外泄）。
# 手法：镜像 judge 的 gateway 夹具——向 assistant server 注入 servicer + 假节点，
#       沿 out_stream 收 ChatJob、以 _route 推预设 ChatDelta/ChatDone 序列。

import asyncio
import json
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.assistant_gateway.gen.assistant.v1 import assistant_pb2
from app.config import settings
from app.models import (AssistantConversation, AssistantMessage, Contest,
                        ContestParticipant, ContestRule, Problem, Submission,
                        SubmissionStatus, User)

from tests.conftest import (add_fake_assistant_node, auth_header, make_user,
                            push_assistant_events, take_assistant_job,
                            take_tool_results)

pytestmark = pytest.mark.asyncio

_display_seq = 1000


async def _mk_problem(sm, owner: User, *, is_public=True,
                      secret="SECRET-SOLUTION-CODE") -> Problem:
    """直插一道题（config 塞标程密钥，验证任何工具返回都不带它）"""
    global _display_seq
    _display_seq += 1
    async with sm() as db:
        p = Problem(display_id=_display_seq, title="求和", description="输入两数求和",
                    difficulty=2, tags=["模拟"], owner_type="user", owner_id=owner.id,
                    is_public=is_public, archived=False,
                    config={"time_limit_ms": 1000, "memory_limit_mb": 128,
                            "solution_code": secret})
        db.add(p)
        await db.commit()
        await db.refresh(p)
        return p


def _done(job_id, text="答案是 3"):
    return assistant_pb2.ChatDone(
        job_id=job_id, stop_reason="end_turn", input_tokens=5, output_tokens=3,
        content_json=json.dumps([{"type": "text", "text": text}], ensure_ascii=False))


def _delta_text(job_id, chunk):
    return assistant_pb2.ChatDelta(job_id=job_id, text_chunk=chunk)


def _delta_tool(job_id, *, tid, name, args: dict):
    return assistant_pb2.ChatDelta(job_id=job_id, tool_use=assistant_pb2.ToolUse(
        id=tid, name=name, input_json=json.dumps(args, ensure_ascii=False)))


def _sse_events(text: str) -> list[tuple[str, dict]]:
    """解析 SSE 帧 → [(event, data)]"""
    out = []
    for frame in text.split("\n\n"):
        ev, data = None, None
        for line in frame.strip().splitlines():
            if line.startswith("event: "):
                ev = line[7:]
            elif line.startswith("data: "):
                data = json.loads(line[6:])
        if ev:
            out.append((ev, data))
    return out


async def _chat(client, headers, gw, *, message="1+1 等于几？", context=None, events=None):
    """完整一轮 SSE 对话：起节点 → 收 ChatJob → 推事件 → 等响应。返回 (job, resp, node)

    events 可为事件工厂 job_id -> list（需要引用 job_id 时用），省略则默认两段文本 + done。"""
    node = add_fake_assistant_node(gw)
    task = asyncio.create_task(client.post(
        "/assistant/chat",
        json={"message": message, "context": context or {}}, headers=headers))
    job = await take_assistant_job(node)
    evts = events(job.job_id) if callable(events) else \
        [_delta_text(job.job_id, "答案"), _done(job.job_id)]
    push_assistant_events(gw, job, evts)
    resp = await asyncio.wait_for(task, timeout=15)
    return job, resp, node


# ---------------- 会话 CRUD ----------------

async def test_conversation_crud_and_ownership(client, normal_user, admin_user,
                                               assistant_gateway, db_sessionmaker):
    h = await auth_header(normal_user)
    r = await client.post("/assistant/conversations",
                          json={"type": "problem", "problem_id": 1}, headers=h)
    assert r.status_code == 201, r.text
    conv = r.json()
    assert conv["title"] == "新对话" and conv["context"]["type"] == "problem"

    r = await client.get("/assistant/conversations", headers=h)
    assert r.status_code == 200 and [c["id"] for c in r.json()] == [conv["id"]]

    r = await client.get(f"/assistant/conversations/{conv['id']}/messages", headers=h)
    assert r.status_code == 200 and r.json() == []

    # 他人会话按「不存在」处理（防枚举 404）
    async with db_sessionmaker() as db:
        other = await make_user(db, "mallory")
    r = await client.get(f"/assistant/conversations/{conv['id']}/messages",
                         headers=await auth_header(other))
    assert r.status_code == 404
    r = await client.delete(f"/assistant/conversations/{conv['id']}",
                            headers=await auth_header(other))
    assert r.status_code == 404

    r = await client.delete(f"/assistant/conversations/{conv['id']}", headers=h)
    assert r.status_code == 200
    r = await client.get("/assistant/conversations", headers=h)
    assert r.json() == []


async def test_conversations_require_login(client):
    assert (await client.get("/assistant/conversations")).status_code == 401
    assert (await client.post("/assistant/conversations", json={})).status_code == 401


# ---------------- chat SSE 端到端 ----------------

async def test_chat_sse_stream_and_persist(client, normal_user, assistant_gateway,
                                           db_sessionmaker):
    h = await auth_header(normal_user)
    job, resp, node = await _chat(client, h, assistant_gateway)
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/event-stream")

    # 下发的 ChatJob：模型名、system 骨架、messages 与 tools 声明
    assert job.model == settings.assistant_model
    assert "编程助教" in job.system
    msgs = json.loads(job.messages_json)
    assert msgs[-1]["role"] == "user" and msgs[-1]["content"][0]["text"] == "1+1 等于几？"
    tool_names = {t["name"] for t in json.loads(job.tools_json)}
    assert tool_names == {"get_problem", "get_submission", "list_case_results",
                          "run_on_sample", "search_problems", "get_my_stats", "get_hint"}

    evs = _sse_events(resp.text)
    assert [e for e, _ in evs] == ["text_delta", "done"]
    assert evs[0][1] == {"text": "答案"}
    done = evs[1][1]
    assert done["stop_reason"] == "end_turn" and done["output_tokens"] == 3
    conv_id = done["conversation_id"]
    assert isinstance(conv_id, str)  # 雪花 ID 字符串化，前端不得 Number()

    # user + assistant 双消息落库；会话标题=首消息截断
    async with db_sessionmaker() as db:
        conv = await db.get(AssistantConversation, int(conv_id))
        assert conv.user_id == normal_user.id and conv.title.startswith("1+1")
        rows = list(await db.scalars(select(AssistantMessage).where(
            AssistantMessage.conversation_id == int(conv_id))))
    assert [m.role for m in rows] == ["user", "assistant"]
    assert rows[1].content[0]["text"] == "答案是 3"

    # 续聊：历史文本进 messages_json（不带工具块）；复用同一节点（_dispatch 选首个有空闲者）
    task = asyncio.create_task(client.post(
        "/assistant/chat", json={"conversation_id": conv_id, "message": "再讲讲"}, headers=h))
    job2 = await take_assistant_job(node)
    hist = json.loads(job2.messages_json)
    assert [m["role"] for m in hist] == ["user", "assistant", "user"]
    push_assistant_events(assistant_gateway, job2, [_done(job2.job_id)])
    assert (await asyncio.wait_for(task, timeout=15)).status_code == 200


async def test_chat_error_event_from_node(client, normal_user, assistant_gateway):
    node = add_fake_assistant_node(assistant_gateway)
    task = asyncio.create_task(client.post(
        "/assistant/chat", json={"message": "hi"},
        headers=await auth_header(normal_user)))
    job = await take_assistant_job(node)
    push_assistant_events(assistant_gateway, job,
                          [_delta_text(job.job_id, "开头"),
                           assistant_pb2.ChatError(job_id=job.job_id, message="模型调用失败")])
    resp = await asyncio.wait_for(task, timeout=15)
    evs = _sse_events(resp.text)
    assert [e for e, _ in evs] == ["text_delta", "error"]
    assert evs[1][1] == {"message": "模型调用失败"}


async def test_chat_503_without_node_or_gateway(client, normal_user, assistant_gateway):
    h = await auth_header(normal_user)
    # 网关注入但零节点在线
    r = await client.post("/assistant/chat", json={"message": "hi"}, headers=h)
    assert r.status_code == 503
    # 网关完全未启动
    from app.assistant_gateway import server as as_server
    as_server._gateway = None
    r = await client.post("/assistant/chat", json={"message": "hi"}, headers=h)
    assert r.status_code == 503
    as_server._gateway = assistant_gateway


# ---------------- 红线：比赛进行中禁用 ----------------

async def _mk_contest(sm, *, start_off_min=-30, duration_min=120) -> Contest:
    now = datetime.now(timezone.utc)
    async with sm() as db:
        c = Contest(title="周赛", rule=ContestRule.ACM,
                    start_at=now + timedelta(minutes=start_off_min),
                    end_at=now + timedelta(minutes=start_off_min + duration_min),
                    board_freeze_minutes=0, owner_type="user", owner_id=1)
        db.add(c)
        await db.commit()
        await db.refresh(c)
        return c


async def _join(sm, contest: Contest, user: User):
    async with sm() as db:
        db.add(ContestParticipant(contest_id=contest.id, user_id=user.id))
        await db.commit()


async def test_contest_active_bans_participant(client, normal_user, assistant_gateway,
                                               db_sessionmaker):
    c = await _mk_contest(db_sessionmaker)
    await _join(db_sessionmaker, c, normal_user)
    add_fake_assistant_node(assistant_gateway)  # 先过容量关，才轮到禁用判定
    r = await client.post("/assistant/chat", json={"message": "hi"},
                          headers=await auth_header(normal_user))
    assert r.status_code == 403
    detail = r.json()["detail"]
    assert detail["reason"] == "contest_active"
    assert str(detail["contest_id"]) == str(c.id)

    # 赛后自动恢复
    async with db_sessionmaker() as db:
        cc = await db.get(Contest, c.id)
        cc.end_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        await db.commit()
    _, resp, _ = await _chat(client, await auth_header(normal_user), assistant_gateway)
    assert resp.status_code == 200


async def test_contest_active_not_applied_to_non_participant_or_admin(
        client, normal_user, admin_user, assistant_gateway, db_sessionmaker):
    c = await _mk_contest(db_sessionmaker)
    # 未报名的普通用户：不受限
    _, resp, _ = await _chat(client, await auth_header(normal_user), assistant_gateway)
    assert resp.status_code == 200
    # ADMIN 报名进行中比赛也豁免（排查/验题需要）
    await _join(db_sessionmaker, c, admin_user)
    _, resp, _ = await _chat(client, await auth_header(admin_user), assistant_gateway)
    assert resp.status_code == 200


# ---------------- 日配额 ----------------

async def test_daily_quota(client, normal_user, assistant_gateway, monkeypatch):
    monkeypatch.setattr(settings, "assistant_daily_quota", 1)
    _, resp, _ = await _chat(client, await auth_header(normal_user), assistant_gateway)
    assert resp.status_code == 200          # 第 1 轮放行（检查时已用 0）
    add_fake_assistant_node(assistant_gateway, node_id="q2")  # 第 2 轮过容量关，才轮到配额
    r = await client.post("/assistant/chat", json={"message": "hi"},
                          headers=await auth_header(normal_user))
    assert r.status_code == 429
    assert r.json()["detail"]["reason"] == "daily_quota"


# ---------------- 工具执行：权限与禁读 ----------------

async def test_tool_get_problem_never_leaks_solution(client, normal_user, assistant_gateway,
                                                     db_sessionmaker):
    p = await _mk_problem(db_sessionmaker, normal_user)
    job, resp, node = await _chat(
        client, await auth_header(normal_user), assistant_gateway,
        events=lambda jid: [_delta_tool(jid, tid="toolu_1", name="get_problem",
                                        args={"display_id": p.display_id}),
                            _done(jid)])
    tr = await take_tool_results(node, 1)
    assert tr[0].tool_use_id == "toolu_1" and tr[0].is_error is False
    # 契约回归：content_json 必须是合法 JSON 串（节点侧 json.loads 组 tool_result 块），
    # 曾直接回填裸文本导致真节点 JSONDecodeError（2026-09-08 联调发现）
    assert "<tool_data>" in json.loads(tr[0].content_json)
    assert "SECRET-SOLUTION-CODE" not in tr[0].content_json
    assert "solution_code" not in tr[0].content_json
    # SSE 侧对应 tool_start / tool_result
    assert [e for e, _ in _sse_events(resp.text)] == ["tool_start", "tool_result", "done"]


async def test_tool_denied_for_missing_submission_and_unknown_tools(
        client, normal_user, assistant_gateway, db_sessionmaker):
    async with db_sessionmaker() as db:
        victim = await make_user(db, "victim")
    p = await _mk_problem(db_sessionmaker, victim)
    async with db_sessionmaker() as db:
        sub = Submission(user_id=victim.id, problem_id=p.id, language="python3.12",
                         code_key="k", code="s3cret-code\nprint(1)",
                         status=SubmissionStatus.WRONG_ANSWER)
        db.add(sub)
        await db.commit()
        await db.refresh(sub)
        victim_h = await auth_header(victim)

    node = add_fake_assistant_node(assistant_gateway)
    task = asyncio.create_task(client.post(
        "/assistant/chat", json={"message": "诊断"}, headers=victim_h))
    job = await take_assistant_job(node)
    push_assistant_events(assistant_gateway, job, [
        _delta_tool(job.job_id, tid="t0", name="get_submission",
                    args={"submission_id": str(sub.id)}),                      # 本人提交：应成功
        _delta_tool(job.job_id, tid="t1", name="get_submission",
                    args={"submission_id": str(sub.id + 999)}),                 # 不存在
        _delta_tool(job.job_id, tid="t2", name="drop_database", args={}),       # 未知工具
        _delta_tool(job.job_id, tid="t3", name="get_hint", args={"level": 1}),  # 无题目上下文
        _done(job.job_id)])
    resp = await asyncio.wait_for(task, timeout=15)
    tr = await take_tool_results(node, 4)
    assert [t.is_error for t in tr] == [False, True, True, True]
    # 本人提交可查（代码本来就对本人可见），但他人（normal_user）视角无从发起——权限按 current_user
    assert "s3cret-code" in tr[0].content_json
    assert "不存在" in tr[1].content_json
    assert "未知工具" in tr[2].content_json
    assert "没有题目上下文" in tr[3].content_json
    assert [e for e, _ in _sse_events(resp.text)] == \
        ["tool_start", "tool_result"] * 4 + ["done"]


async def test_tool_other_users_submission_invisible(client, normal_user, assistant_gateway,
                                                     db_sessionmaker):
    """越权查他人提交：is_error 且不带代码（防枚举「不存在或无权查看」）"""
    async with db_sessionmaker() as db:
        victim = await make_user(db, "victim2")
    p = await _mk_problem(db_sessionmaker, victim)
    async with db_sessionmaker() as db:
        sub = Submission(user_id=victim.id, problem_id=p.id, language="python3.12",
                         code_key="k", code="s3cret-code\nprint(1)",
                         status=SubmissionStatus.WRONG_ANSWER)
        db.add(sub)
        await db.commit()
        await db.refresh(sub)

    node = add_fake_assistant_node(assistant_gateway)
    task = asyncio.create_task(client.post(
        "/assistant/chat", json={"message": "看看他的代码"},
        headers=await auth_header(normal_user)))
    job = await take_assistant_job(node)
    push_assistant_events(assistant_gateway, job, [
        _delta_tool(job.job_id, tid="t1", name="get_submission",
                    args={"submission_id": str(sub.id)}),
        _done(job.job_id)])
    await asyncio.wait_for(task, timeout=15)
    tr = await take_tool_results(node, 1)
    assert tr[0].is_error is True
    assert "s3cret-code" not in tr[0].content_json


async def test_tool_get_hint_with_problem_context_ok(client, normal_user, assistant_gateway,
                                                     db_sessionmaker):
    p = await _mk_problem(db_sessionmaker, normal_user)
    job, resp, node = await _chat(
        client, await auth_header(normal_user), assistant_gateway,
        context={"type": "problem", "problem_id": p.id},
        events=lambda jid: [_delta_tool(jid, tid="t1", name="get_hint", args={"level": 1}),
                            _done(jid)])
    tr = await take_tool_results(node, 1)
    assert tr[0].is_error is False and "hint" in tr[0].content_json
    # system prompt 带上了题目上下文
    assert "当前上下文是一道题" in job.system
