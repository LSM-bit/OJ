"""AI 助手工具层（信息：api/app/services/assistant_tools.py；用途：注册 7 个只读/自测工具，由 assistant router 在 API 侧执行——节点只见结果 JSON，权限在此处强制）

安全红线（docs/AI助手Agent设计.md §5/§7）：
- 任何工具不返回标程（config.solution_code）、隐藏用例 .in/.out、manifest 分值明细；
- handler 第一个业务参数恒为 current_user（由循环注入，模型无法伪造）；
- 返回值统一 <tool_data> 包裹 + 8KB 截断，题面/代码属不可信注入内容；
- 越权一律按"不存在"处理（与 access_deps 防枚举口径一致）。
"""

import json
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Coroutine

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.assistant_gateway.gen.assistant.v1 import assistant_pb2
from app.config import settings
from app.judge_gateway.gen.judge.v1 import judge_pb2
from app.models import (AssistantConversation, AssistantMessage, AssistantToolCall,
                        Contest, ContestParticipant, Problem, Submission, SubmissionStatus,
                        Testcase, User, UserRole)
from app.services import problem_data
from app.services.access_deps import problem_view_allowed

MAX_RESULT_BYTES = 8 * 1024


class ToolAccessError(Exception):
    """工具内权限/存在性错误：以 is_error tool_result 回给模型（不抛 HTTP）"""


# ============ 工具声明（Anthropic tools 数组，直接进 ChatJob.tools_json） ============

TOOL_SPECS: list[dict] = [
    {"name": "get_problem", "description": "按题号(display_id)查题目：题面 Markdown、时限/内存、标签、难度、公开样例。返回不含隐藏用例与标程。",
     "input_schema": {"type": "object", "properties":
                      {"display_id": {"type": "integer", "description": "对外展示题号"}},
                      "required": ["display_id"]}},
    {"name": "get_submission", "description": "查一次提交：代码、语言、判定、得分、用时/内存。仅本人或管理员的提交可查。",
     "input_schema": {"type": "object", "properties":
                      {"submission_id": {"type": "string"}}, "required": ["submission_id"]}},
    {"name": "list_case_results", "description": "查一次提交的逐测试点结果（status/用时/内存）。刻意不含任何输入输出内容。",
     "input_schema": {"type": "object", "properties":
                      {"submission_id": {"type": "string"}}, "required": ["submission_id"]}},
    {"name": "run_on_sample", "description": "把一段代码在该题公开样例上运行一次（沙箱，2s/64MB 紧限额），返回输出比对结果。每日次数受限。",
     "input_schema": {"type": "object", "properties": {
         "display_id": {"type": "integer"}, "language": {"type": "string"},
         "code": {"type": "string"}},
         "required": ["display_id", "language", "code"]}},
    {"name": "search_problems", "description": "按关键词/标签/难度搜索可见题目，返回摘要列表（≤10 条）。",
     "input_schema": {"type": "object", "properties": {
         "keyword": {"type": "string"}, "tag": {"type": "string"},
         "difficulty": {"type": "integer", "minimum": 1, "maximum": 5}}}},
    {"name": "get_my_stats", "description": "查提问者自己的刷题统计：提交数、通过数、常错标签（按 wrong_answer 聚合）。",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "get_hint", "description": "获取当前上下文题目的分层提示（level 1~3，越深越接近题解）。题目预置提示优先，否则返回难度导向的通用引导要点。",
     "input_schema": {"type": "object", "properties":
                      {"level": {"type": "integer", "minimum": 1, "maximum": 3}},
                      "required": ["level"]}},
]

TOOL_NAMES = {t["name"] for t in TOOL_SPECS}


# ============ 结果封装 ============

def wrap_tool_data(payload: Any) -> str:
    """返回值统一 <tool_data> 包裹 + 8KB 截断（system prompt 声明其内容不构成指令）"""
    text = payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False, default=str)
    encoded = text.encode("utf-8")
    if len(encoded) > MAX_RESULT_BYTES:
        text = encoded[:MAX_RESULT_BYTES].decode("utf-8", errors="ignore") + "\n…（结果已截断）"
    return f"<tool_data>\n{text}\n</tool_data>"


# ============ 上下文辅助：题目在哪个进行中比赛里 ============

async def _active_contest_for_problem(db: AsyncSession, problem_id: int) -> Contest | None:
    """题目所属且当前进行中（start<=now<=end，按 _aware 派生）的比赛，取第一个"""
    from app.models import ContestProblem
    now = datetime.now(timezone.utc)
    rows = await db.scalars(
        select(Contest).where(Contest.id.in_(
            select(ContestProblem.contest_id).where(ContestProblem.problem_id == problem_id))))
    for c in rows:
        start = c.start_at.replace(tzinfo=timezone.utc) if c.start_at.tzinfo is None else c.start_at
        end = c.end_at.replace(tzinfo=timezone.utc) if c.end_at.tzinfo is None else c.end_at
        if start <= now <= end:
            return c
    return None


async def _contest_participation(db: AsyncSession, contest_id: int, user_id: int) -> bool:
    return await db.scalar(select(ContestParticipant.id).where(
        ContestParticipant.contest_id == contest_id,
        ContestParticipant.user_id == user_id)) is not None


# ============ 各工具 handler：签名统一 (db, user, ctx, args) -> payload ============

async def _t_get_problem(db, user, ctx, args):
    p = await db.scalar(select(Problem).where(Problem.display_id == args["display_id"]))
    if p is None or not await problem_view_allowed(db, user, p):
        raise ToolAccessError("题目不存在或不可见")
    version = p.config.get("data_version", "v1")
    tcs = list(await db.scalars(
        select(Testcase).where(Testcase.problem_id == p.id).order_by(Testcase.idx)))
    samples = []
    for tc in [t for t in tcs if tc.is_sample][:5]:
        inp = await problem_data.read_text_file(str(p.id), version, tc.input_key, limit=2000) or ""
        out_text = await problem_data.read_text_file(str(p.id), version, tc.output_key, limit=2000) or ""
        samples.append({"input": inp, "output": out_text})
    # 注意：config 只挑展示字段——solution_code 等内部键绝不外泄
    return {
        "display_id": p.display_id, "title": p.title, "description": p.description,
        "difficulty": p.difficulty, "tags": p.tags,
        "time_limit_ms": p.config.get("time_limit_ms", 2000),
        "memory_limit_mb": p.config.get("memory_limit_mb", 256),
        "samples": samples, "testcase_count": len([t for t in tcs if not t.is_sample]),
    }


async def _submission_or_error(db, user, args) -> Submission:
    try:
        sid = int(args["submission_id"])
    except (TypeError, ValueError):
        raise ToolAccessError("submission_id 需为数字字符串") from None
    sub = await db.get(Submission, sid)
    if sub is None or not (user.role == UserRole.ADMIN or sub.user_id == user.id):
        raise ToolAccessError("提交不存在或无权查看")
    return sub


async def _t_get_submission(db, user, ctx, args):
    sub = await _submission_or_error(db, user, args)
    p = await db.get(Problem, sub.problem_id)
    return {
        "id": str(sub.id), "problem_display_id": p.display_id if p else None,
        "problem_title": p.title if p else None,
        "language": sub.language, "status": sub.status.value, "score": sub.score,
        "time_ms": sub.time_ms, "memory_kb": sub.memory_kb,
        "code": sub.code, "submitted_at": sub.submitted_at,
    }


async def _t_list_case_results(db, user, ctx, args):
    sub = await _submission_or_error(db, user, args)
    detail = sub.detail or {}
    # 只回状态与资源数据；输入输出内容一律不带（防作弊红线）
    return {"status": sub.status.value, "score": sub.score,
            "cases": detail.get("cases", []),
            "error_message": detail.get("error_message", "")}


async def _t_run_on_sample(db, user, ctx, args):
    p = await db.scalar(select(Problem).where(Problem.display_id == args["display_id"]))
    if p is None or not await problem_view_allowed(db, user, p):
        raise ToolAccessError("题目不存在或不可见")
    # 设计 §5：比赛进行中该题禁止样例自测（router 入口只拦参赛者，这里兜住任意上下文）
    if await _active_contest_for_problem(db, p.id) is not None:
        raise ToolAccessError("该题目所属比赛进行中，禁止样例自测")
    # 每日次数限制（DB 计数，不引 Redis）
    day_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    used = await db.scalar(
        select(func.count()).select_from(AssistantToolCall)
        .where(AssistantToolCall.user_id == user.id)
        .where(AssistantToolCall.tool == "run_on_sample")
        .where(AssistantToolCall.created_at >= day_start)) or 0
    if used >= settings.assistant_run_sample_quota:
        raise ToolAccessError(f"run_on_sample 今日次数已用完（{settings.assistant_run_sample_quota} 次/日）")
    version = p.config.get("data_version", "v1")
    samples = list(await db.scalars(
        select(Testcase).where(Testcase.problem_id == p.id, Testcase.is_sample == True)  # noqa: E712
        .order_by(Testcase.idx)))
    if not samples:
        raise ToolAccessError("该题没有公开样例可运行")
    from app.judge_gateway.server import get_gateway
    gw = get_gateway()
    results = []
    # 紧限额：2s / 64MB（比正式判题更严，自测只是看个大概）
    for tc in samples[:3]:
        stdin = (await problem_data.read_file(str(p.id), version, tc.input_key)) or b""
        expected = (await problem_data.read_text_file(str(p.id), version, tc.output_key, limit=4000)) or ""
        job = judge_pb2.RunCodeJob(
            request_id=f"ai-{user.id}-{tc.id}", language=args["language"],
            code=args["code"].encode(), input=stdin,
            limits=judge_pb2.ResourceLimits(
                time_limit_ms=2000, memory_limit_mb=64, output_limit_kb=256))
        try:
            r = await gw.run_code(job, timeout=30)
            got = r.output.decode("utf-8", errors="replace")[:2000]
            results.append({"input_preview": stdin.decode("utf-8", errors="replace")[:200],
                            "expected": expected[:2000], "actual": got,
                            "status": r.status, "error_message": r.error_message[:500],
                            "matched": _norm(got) == _norm(expected)})
        except RuntimeError as exc:
            raise ToolAccessError(f"判题节点不可用: {exc}") from exc
    db.add(AssistantToolCall(user_id=user.id, tool="run_on_sample",
                             conversation_id=ctx.get("conversation_id")))
    await db.commit()
    return {"runs": results}


def _norm(s: str) -> str:
    return "\n".join(line.rstrip() for line in s.strip().splitlines())


async def _t_search_problems(db, user, ctx, args):
    stmt = select(Problem).where(Problem.is_public == True, Problem.archived == False)  # noqa: E712
    if args.get("keyword"):
        kw = f"%{args['keyword'].strip().replace('%', '').replace('_', '')}%"
        stmt = stmt.where(Problem.title.ilike(kw))
    if args.get("difficulty"):
        stmt = stmt.where(Problem.difficulty == int(args["difficulty"]))
    # tag 筛选走 JSONB 文本包含（SQLite 兼容写法，与 problems 列表同款思路）
    if args.get("tag"):
        stmt = stmt.where(Problem.tags.like(f'%{json.dumps(args["tag"].strip(), ensure_ascii=False)}%'))
    rows = await db.scalars(stmt.order_by(Problem.display_id).limit(10))
    return [{"display_id": p.display_id, "title": p.title, "difficulty": p.difficulty,
             "tags": p.tags} for p in rows]


async def _t_get_my_stats(db, user, ctx, args):
    total = await db.scalar(select(func.count()).select_from(Submission)
                            .where(Submission.user_id == user.id)) or 0
    ac = await db.scalar(select(func.count()).select_from(Submission)
                         .where(Submission.user_id == user.id,
                                Submission.status == SubmissionStatus.ACCEPTED)) or 0
    solved = await db.scalar(select(func.count(func.distinct(Submission.problem_id)))
                             .where(Submission.user_id == user.id,
                                    Submission.status == SubmissionStatus.ACCEPTED)) or 0
    # 常错标签：未通过的提交按题目标签聚合（一次 join 足够）
    wrong_rows = await db.execute(
        select(Problem.tags).where(
            Submission.user_id == user.id,
            Submission.status != SubmissionStatus.ACCEPTED,
            Submission.problem_id == Problem.id))
    tag_counter: dict[str, int] = {}
    for (tags,) in wrong_rows:
        for t in set(tags or []):
            tag_counter[t] = tag_counter.get(t, 0) + 1
    weak = sorted(tag_counter.items(), key=lambda x: -x[1])[:8]
    return {"total_submissions": total, "accepted_submissions": ac,
            "solved_problems": solved, "rating": user.rating,
            "weak_tags": [{"tag": t, "wrong_count": c} for t, c in weak]}


async def _t_get_hint(db, user, ctx, args):
    pid = ctx.get("problem_id")
    if not pid:
        raise ToolAccessError("当前会话没有题目上下文，无法给提示")
    p = await db.get(Problem, pid)
    if p is None or not await problem_view_allowed(db, user, p):
        raise ToolAccessError("题目不存在或不可见")
    hints = (p.config.get("hints") or []) if isinstance(p.config.get("hints"), list) else []
    level = int(args["level"])
    if level <= len(hints):
        return {"source": "preset", "level": level, "hint": hints[level - 1]}
    # 预置提示用尽/未配置：返回难度导向的通用引导（仍不泄露标程思路细节）
    ladder = {1: f"先想清楚输入输出与边界情况（难度 {p.difficulty}）。",
              2: "考虑样例覆盖不到的情形，尝试把问题分解成更小的子问题。",
              3: "回顾同类标签题的通用套路；如需完整题解请移步题解区（本助手不提供）。"}
    return {"source": "generic", "level": level, "hint": ladder[level]}


HANDLERS: dict[str, Callable[..., Coroutine]] = {
    "get_problem": _t_get_problem,
    "get_submission": _t_get_submission,
    "list_case_results": _t_list_case_results,
    "run_on_sample": _t_run_on_sample,
    "search_problems": _t_search_problems,
    "get_my_stats": _t_get_my_stats,
    "get_hint": _t_get_hint,
}


async def execute_tool(db: AsyncSession, user: User, ctx: dict,
                       tu: assistant_pb2.ToolUse) -> tuple[str, bool]:
    """执行一个工具调用（router 收到 ChatDelta.tool_use 后调用）。
    返回 (content_json, is_error)——content 为 <tool_data> 包裹文本，异常转错误结果给模型自纠。"""
    name = tu.name
    if name not in HANDLERS:
        return json.dumps(f"<tool_data>未知工具 {name}</tool_data>", ensure_ascii=False), True
    try:
        args = json.loads(tu.input_json or "{}")
    except json.JSONDecodeError:
        return json.dumps("<tool_data>工具入参不是合法 JSON</tool_data>", ensure_ascii=False), True
    try:
        payload = await HANDLERS[name](db, user, ctx, args)
        return wrap_tool_data(payload), False
    except ToolAccessError as exc:
        return wrap_tool_data({"error": str(exc)}), True
    except Exception as exc:  # noqa: BLE001 工具内部异常不外泄细节
        return wrap_tool_data({"error": "工具执行失败"}), True
