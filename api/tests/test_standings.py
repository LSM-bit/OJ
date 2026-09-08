"""榜单服务单元测试：ACM/OI 排名 / 罚时 / 封榜 / 提交重放逻辑

不走 HTTP，直接在测试库造数据后调用 compute_standings()。
"""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Contest, ContestParticipant, ContestProblem, ContestRule, Problem,
    Submission, SubmissionStatus,
)
from app.services.standings import compute_standings, is_frozen

pytestmark = pytest.mark.asyncio


async def _mk_contest(db: AsyncSession, owner, *, rule=ContestRule.ACM,
                      start_offset_min=-30, duration_min=120, freeze=0) -> Contest:
    now = datetime.now(timezone.utc)
    c = Contest(
        title="test-contest", rule=rule,
        start_at=now + timedelta(minutes=start_offset_min),
        end_at=now + timedelta(minutes=start_offset_min + duration_min),
        board_freeze_minutes=freeze, owner_type="user", owner_id=owner.id,
    )
    db.add(c)
    await db.flush()
    return c


_display_id_seq = 0


async def _mk_problem(db: AsyncSession, owner, score_total=100) -> Problem:
    global _display_id_seq
    _display_id_seq += 1
    p = Problem(display_id=_display_id_seq, title="P", description="", owner_type="user",
                owner_id=owner.id, config={"score_total": score_total})
    db.add(p)
    await db.flush()
    return p


async def _add_contest_problem(db: AsyncSession, contest: Contest, problem: Problem, alias: str):
    db.add(ContestProblem(contest_id=contest.id, problem_id=problem.id, alias=alias))


async def _join(db: AsyncSession, contest: Contest, user):
    db.add(ContestParticipant(contest_id=contest.id, user_id=user.id))


async def _submit(db: AsyncSession, contest: Contest, user, problem: Problem,
                  status: SubmissionStatus, minutes_after_start: float):
    """在比赛开始后第 N 分钟提交（status 直接落库，模拟判题结果）"""
    db.add(Submission(
        user_id=user.id, problem_id=problem.id, contest_id=contest.id,
        language="python3.12", code_key="k",
        status=status,
        submitted_at=contest.start_at + timedelta(minutes=minutes_after_start),
    ))
    await db.flush()


async def test_acm_ranking_penalty_and_order(db_sessionmaker):
    """ACM：过题数优先，其次罚时（过题时刻 + 20min×错次）"""
    async with db_sessionmaker() as db:
        from tests.conftest import make_user
        admin = await make_user(db, "owner_acm")
        u1 = await make_user(db, "u1")
        u2 = await make_user(db, "u2")

        c = await _mk_contest(db, admin)
        p = await _mk_problem(db, admin)
        await _add_contest_problem(db, c, p, "A")
        await _join(db, c, u1)
        await _join(db, c, u2)

        # u1：第 10 分钟 AC（罚时 10）
        await _submit(db, c, u1, p, SubmissionStatus.ACCEPTED, 10)
        # u2：第 5 分钟 WA + 第 30 分钟 AC（罚时 30 + 20 = 50）
        await _submit(db, c, u2, p, SubmissionStatus.WRONG_ANSWER, 5)
        await _submit(db, c, u2, p, SubmissionStatus.ACCEPTED, 30)
        await db.commit()

        out = await compute_standings(db, c)

    assert out["phase"] == "running"
    assert not out["frozen"]
    rows = out["rows"]
    assert len(rows) == 2
    assert rows[0]["username"] == "u1"  # 同 1 题，罚时 10 < 50
    assert rows[0]["penalty"] == 10
    assert rows[1]["username"] == "u2"
    assert rows[1]["penalty"] == 50
    assert rows[1]["cells"][0]["attempts"] == 1


async def test_acm_wrong_submissions_before_solve_count(db_sessionmaker):
    """AC 确认之后的错误提交不计罚时（标准 ACM 规则）"""
    async with db_sessionmaker() as db:
        from tests.conftest import make_user
        admin = await make_user(db, "owner_a2")
        u1 = await make_user(db, "u1b")

        c = await _mk_contest(db, admin)
        p = await _mk_problem(db, admin)
        await _add_contest_problem(db, c, p, "A")
        await _join(db, c, u1)

        await _submit(db, c, u1, p, SubmissionStatus.WRONG_ANSWER, 5)
        await _submit(db, c, u1, p, SubmissionStatus.ACCEPTED, 20)
        await _submit(db, c, u1, p, SubmissionStatus.WRONG_ANSWER, 40)  # 过题后再错：不计
        await db.commit()

        out = await compute_standings(db, c)
    row = out["rows"][0]
    assert row["penalty"] == 20 + 20 * 1  # 过题时刻 20 + 一次错误罚时
    assert row["cells"][0]["attempts"] == 1


async def test_oi_ranking_by_score(db_sessionmaker):
    """OI：总分排序（过题=满分）"""
    async with db_sessionmaker() as db:
        from tests.conftest import make_user
        admin = await make_user(db, "owner_oi")
        u1 = await make_user(db, "oi1")
        u2 = await make_user(db, "oi2")

        c = await _mk_contest(db, admin, rule=ContestRule.OI)
        pa = await _mk_problem(db, admin, score_total=100)
        pb = await _mk_problem(db, admin, score_total=200)
        await _add_contest_problem(db, c, pa, "A")
        await _add_contest_problem(db, c, pb, "B")
        await _join(db, c, u1)
        await _join(db, c, u2)

        # u1：只过 A（100 分）
        await _submit(db, c, u1, pa, SubmissionStatus.ACCEPTED, 10)
        # u2：过 A+B（300 分）
        await _submit(db, c, u2, pa, SubmissionStatus.ACCEPTED, 15)
        await _submit(db, c, u2, pb, SubmissionStatus.ACCEPTED, 40)
        await db.commit()

        out = await compute_standings(db, c)
    rows = out["rows"]
    assert rows[0]["username"] == "oi2"
    assert rows[0]["score"] == 300
    assert rows[1]["username"] == "oi1" and rows[1]["score"] == 100


async def test_freeze_window_pending(db_sessionmaker):
    """封榜后：未过题的错误提交进 pending，榜单不增长 attempts；过题标 frozen"""
    async with db_sessionmaker() as db:
        from tests.conftest import make_user
        admin = await make_user(db, "owner_fz")
        u1 = await make_user(db, "fz1")
        u2 = await make_user(db, "fz2")

        # 比赛时长 120min，封榜最后 30min；已开始 100min（处于封榜窗口内）
        c = await _mk_contest(db, admin, start_offset_min=-100, duration_min=120, freeze=30)
        p = await _mk_problem(db, admin)
        await _add_contest_problem(db, c, p, "A")
        await _join(db, c, u1)
        await _join(db, c, u2)

        assert is_frozen(c, c.start_at + timedelta(minutes=89)) is False
        assert is_frozen(c, c.start_at + timedelta(minutes=91)) is True

        # u1：封榜前 AC（正常显示）
        await _submit(db, c, u1, p, SubmissionStatus.ACCEPTED, 20)
        # u2：封榜后 AC（frozen 显示 "?"）+ 封榜后 WA（pending）
        await _submit(db, c, u2, p, SubmissionStatus.WRONG_ANSWER, 95)
        await _submit(db, c, u2, p, SubmissionStatus.ACCEPTED, 100)
        await db.commit()

        out = await compute_standings(db, c)
    assert out["frozen"] is True
    r1, r2 = out["rows"]
    assert r1["username"] == "fz1"
    assert r1["cells"][0]["frozen"] is False
    # u2 封榜后：WA 计 pending 而非 attempts；AC 过题 frozen=True
    r2_cells = r2["cells"][0]
    assert r2_cells["pending"] == 1
    assert r2_cells["attempts"] == 0
    assert r2_cells["frozen"] is True
    # u2 罚时不增长（过题被冻结）
    assert r2["solved"] == 0  # 冻结的过题不计入已解题数


async def test_unfreeze_after_contest_ends(db_sessionmaker):
    """比赛结束后封榜解除：全部揭晓"""
    async with db_sessionmaker() as db:
        from tests.conftest import make_user
        admin = await make_user(db, "owner_uf")
        u1 = await make_user(db, "uf1")

        # 已结束 60min 的比赛（freeze=30，最后一次提交在封榜窗口内）
        now = datetime.now(timezone.utc)
        c = Contest(title="ended", rule=ContestRule.ACM,
                    start_at=now - timedelta(minutes=180),
                    end_at=now - timedelta(minutes=60),
                    board_freeze_minutes=30, owner_type="user", owner_id=admin.id)
        db.add(c)
        await db.flush()
        p = await _mk_problem(db, admin)
        await _add_contest_problem(db, c, p, "A")
        await _join(db, c, u1)
        # 封榜窗口内的提交（end-20min）
        await _submit(db, c, u1, p, SubmissionStatus.ACCEPTED, 160)
        await db.commit()

        out = await compute_standings(db, c)
    assert out["phase"] == "ended"
    assert out["frozen"] is False
    row = out["rows"][0]
    assert row["solved"] == 1
    assert row["cells"][0]["frozen"] is False


async def test_no_submissions_row_zeros(db_sessionmaker):
    """没提交的参赛者显示全零行"""
    async with db_sessionmaker() as db:
        from tests.conftest import make_user
        admin = await make_user(db, "owner_z")
        u1 = await make_user(db, "zz1")

        c = await _mk_contest(db, admin)
        p = await _mk_problem(db, admin)
        await _add_contest_problem(db, c, p, "A")
        await _join(db, c, u1)
        await db.commit()

        out = await compute_standings(db, c)
    row = out["rows"][0]
    assert row["solved"] == 0 and row["penalty"] == 0
    assert row["cells"][0]["solved"] is False
