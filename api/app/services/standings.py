"""比赛服务：榜单计算（ACM/OI 赛制 + 封榜）

榜单数据结构（每参赛者每题一条 cell）：
  cell = {problem_alias, attempts, solved, solve_time_minutes, pending(封榜后未揭晓次数)}

ACM 排名：过题数降序 → 罚时升序（罚时 = 过题时刻总和 + 20 * 错误次数，按分钟）
OI  排名：总分降序 → 最后过题时间升序
"""

import json
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.models import (
    Contest,
    ContestParticipant,
    ContestProblem,
    ContestRule,
    Submission,
    SubmissionStatus,
)

# ACM 赛制每次错误提交罚 20 分钟
ACM_PENALTY_MINUTES = 20


def _ensure_aware(dt: datetime) -> datetime:
    """DB 读回的 datetime 可能丢时区（naive），统一按 UTC 补齐"""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def contest_phase(contest: Contest, now: datetime) -> str:
    start, end = _ensure_aware(contest.start_at), _ensure_aware(contest.end_at)
    if now < start:
        return "upcoming"
    if now > end:
        return "ended"
    return "running"


def is_frozen(contest: Contest, now: datetime) -> bool:
    """封榜窗口：比赛进行中且进入封榜时间后"""
    if contest.board_freeze_minutes <= 0 or contest_phase(contest, now) != "running":
        return False
    freeze_at = _ensure_aware(contest.end_at) - timedelta(minutes=contest.board_freeze_minutes)
    return now >= freeze_at


async def compute_standings(db: AsyncSession, contest: Contest) -> dict[str, Any]:
    """计算一场比赛的完整榜单"""
    now = datetime.now(timezone.utc)
    c_start, c_end = _ensure_aware(contest.start_at), _ensure_aware(contest.end_at)
    frozen = is_frozen(contest, now)

    # 比赛题目（alias 排序 A, B, C...）
    contest_problems, problems = await _load_contest_problems(db, contest.id)
    alias_by_pid = {cp.problem_id: cp.alias for cp in contest_problems}
    score_by_pid = {p.id: p.config.get("score_total", 100) for p in problems}

    # 参赛者（joinedload 预加载 user，避免 async 环境 lazy load 触发 MissingGreenlet）
    participants = await db.scalars(
        select(ContestParticipant)
        .where(ContestParticipant.contest_id == contest.id)
        .options(joinedload(ContestParticipant.user))
    )
    participants = list(participants)

    # 该比赛中产生的所有提交（按时间升序，逐条重放）
    subs = await db.scalars(
        select(Submission)
        .where(Submission.contest_id == contest.id)
        .order_by(Submission.id)
    )
    subs = list(subs)

    cells: dict[tuple[int, int], dict] = {}  # (user_id, problem_id) -> cell
    for sub in subs:
        key = (sub.user_id, sub.problem_id)
        cell = cells.setdefault(key, {
            "alias": alias_by_pid.get(sub.problem_id, "?"),
            "attempts": 0, "solved": False, "solve_time": 0, "pending": 0, "frozen": False,
        })
        solved_now = sub.status == SubmissionStatus.ACCEPTED and not cell["solved"]
        sub_time = _ensure_aware(sub.submitted_at)
        # 封榜期间的新提交：榜单上只显示尝试次数增长，结果冻结
        hidden = frozen and sub_time >= c_end - timedelta(
            minutes=contest.board_freeze_minutes)
        if solved_now:
            cell["solved"] = True
            cell["solve_time"] = int((sub_time - c_start).total_seconds() // 60)
            cell["frozen"] = hidden  # 封榜中过题 → 显示为 "?" 待揭晓
        elif sub.status != SubmissionStatus.ACCEPTED and not cell["solved"]:
            # 过题确认后的错误提交不计罚时（标准 ACM 规则）
            if hidden:
                cell["pending"] += 1
            else:
                cell["attempts"] += 1

    # 按参赛者聚合
    rows = []
    for p in participants:
        user_cells = [cells.get((p.user_id, cp.problem_id), {
            "alias": alias_by_pid[cp.problem_id], "attempts": 0, "solved": False,
            "solve_time": 0, "pending": 0, "frozen": False})
            for cp in contest_problems]
        solved_count = sum(1 for c in user_cells if c["solved"] and not c["frozen"])
        # 封榜中过题（frozen=True）视为未揭晓：不进 solved 数、不参与排名惩罚
        if contest.rule == ContestRule.ACM:
            penalty = sum(
                (c["solve_time"] + ACM_PENALTY_MINUTES * c["attempts"])
                for c in user_cells if c["solved"] and not c["frozen"])
            score = solved_count
        else:  # OI：按题目满分比例给分（简化：过题=满分）
            penalty = max((c["solve_time"] for c in user_cells
                           if c["solved"] and not c["frozen"]), default=0)
            score = sum(score_by_pid.get(pid, 100)
                        for (uid, pid), c in cells.items()
                        if uid == p.user_id and c["solved"])
        rows.append({
            "user_id": p.user_id,
            "username": p.user.username if p.user else f"u{p.user_id}",
            "solved": solved_count, "score": score, "penalty": penalty,
            "cells": user_cells,
        })

    if contest.rule == ContestRule.ACM:
        rows.sort(key=lambda r: (-r["solved"], r["penalty"]))
    else:
        rows.sort(key=lambda r: (-r["score"], r["penalty"]))
    for i, r in enumerate(rows):
        r["rank"] = i + 1

    return {
        "contest_id": contest.id,
        "phase": contest_phase(contest, now),
        "frozen": frozen,
        "rows": rows,
    }


async def _load_contest_problems(db: AsyncSession, contest_id: int):
    """返回 (contest_problems, problems) 两个列表，alias 升序"""
    from app.models import Problem

    cps = await db.scalars(
        select(ContestProblem).where(ContestProblem.contest_id == contest_id)
        .order_by(ContestProblem.alias)
    )
    cps = list(cps)
    pids = [cp.problem_id for cp in cps]
    problems = []
    if pids:
        problems = list(await db.scalars(select(Problem).where(Problem.id.in_(pids))))
    return cps, problems
