"""比赛路由：创建/列表/详情/报名/比赛题目/提交/榜单"""

import json
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Body, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import (
    Contest,
    ContestParticipant,
    ContestProblem,
    ContestRule,
    ContestStatus,
    OwnerType,
    Problem,
    Submission,
    SubmissionStatus,
    TeamMember,
    Testcase,
    User,
    UserRole,
)
from app.judge_gateway.gen.judge.v1 import judge_pb2
from app.judge_gateway.server import get_gateway
from app.routers.submissions import NODE_STATUS_MAP, STATUS_LABEL, _to_out
from app.services.access import require_team_manage
from app.services.access_deps import ContestAccess
from app.services.auth import (
    ContestAdminDep,
    CurrentUser,
    get_current_user,
    get_optional_user,
)
from app.services.standings import compute_standings

router = APIRouter(prefix="/contests", tags=["contests"])


class ContestCreate(BaseModel):
    title: str = Field(min_length=1, max_length=128)
    description: str = ""
    rule: ContestRule = ContestRule.ACM
    start_at: datetime
    end_at: datetime
    board_freeze_minutes: int = Field(default=0, ge=0)
    is_public: bool = True
    owner_type: OwnerType = OwnerType.USER
    team_id: int | None = None
    problem_ids: list[int] = Field(default_factory=list)  # 按 A/B/C 顺序


def _aware(dt: datetime) -> datetime:
    """DB 读回的 datetime 可能丢时区（naive），统一按 UTC 补齐"""
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt


def _contest_out(c: Contest) -> dict:
    now = datetime.now(timezone.utc)
    start, end = _aware(c.start_at), _aware(c.end_at)
    if now < start:
        phase = ContestStatus.UPCOMING
    elif now > end:
        phase = ContestStatus.ENDED
    else:
        phase = ContestStatus.RUNNING
    return {
        "id": c.id, "title": c.title, "rule": c.rule.value, "phase": phase.value,
        "start_at": c.start_at.isoformat(), "end_at": c.end_at.isoformat(),
        "board_freeze_minutes": c.board_freeze_minutes,
        "description": c.description,
        "is_public": c.is_public,
        "owner_type": c.owner_type.value,
    }


@router.post("", status_code=201)
async def create_contest(
    req: ContestCreate, db: AsyncSession = Depends(get_db), user: User = ContestAdminDep
):
    if req.end_at <= req.start_at:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "结束时间必须晚于开始时间")
    # 归属个人或团队（团队需有管理权）
    if req.owner_type == OwnerType.TEAM:
        if not req.team_id:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "缺少 team_id")
        from app.models import Team
        t = await db.get(Team, req.team_id)
        if t is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "团队不存在")
        await require_team_manage(db, req.team_id, user)
        owner_id = req.team_id
    else:
        owner_id = user.id
    # 可添加「我可见」的任意题目（含自己的私有题）；他人私有题不可加（防借比赛泄露）
    from app.services.access import can_view
    seen = set()
    for pid in req.problem_ids:
        if pid in seen:
            continue
        seen.add(pid)
        p = await db.get(Problem, pid)
        if p is None:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"题目 {pid} 不存在")
        if not await can_view(db, user, p.owner_type, p.owner_id, p.is_public):
            raise HTTPException(
                status.HTTP_403_FORBIDDEN, f"题目 {p.display_id} 为他人私有题目，无法添加")
    c = Contest(
        title=req.title, description=req.description, rule=req.rule,
        start_at=req.start_at, end_at=req.end_at,
        board_freeze_minutes=req.board_freeze_minutes,
        is_public=req.is_public, owner_type=req.owner_type, owner_id=owner_id,
    )
    db.add(c)
    await db.flush()
    for i, pid in enumerate(req.problem_ids):
        p = await db.get(Problem, pid)
        if p is None:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"题目 {pid} 不存在")
        db.add(ContestProblem(contest_id=c.id, problem_id=pid,
                              alias=chr(ord("A") + i)))
    await db.commit()
    return {**_contest_out(c), "problems": len(req.problem_ids)}


@router.get("")
async def list_contests(
    db: AsyncSession = Depends(get_db),
    user: User | None = Depends(get_optional_user),
):
    """公有比赛 + 我拥有的 + 我团队的（未登录只看公有）"""
    if user is None:
        stmt = select(Contest).where(Contest.is_public == True)  # noqa: E712
    elif user.role == UserRole.ADMIN:
        stmt = select(Contest)
    else:
        my_team_ids = select(TeamMember.team_id).where(TeamMember.user_id == user.id)
        stmt = select(Contest).where(
            (Contest.is_public == True)  # noqa: E712
            | ((Contest.owner_type == OwnerType.USER) & (Contest.owner_id == user.id))
            | ((Contest.owner_type == OwnerType.TEAM) & Contest.owner_id.in_(my_team_ids)))
    rows = await db.scalars(stmt.order_by(Contest.start_at.desc()).limit(50))
    return [_contest_out(c) for c in rows]


@router.get("/{contest_id}")
async def contest_detail(
    contest_id: int, c: Contest = Depends(ContestAccess("view")),
    db: AsyncSession = Depends(get_db),
    user: User | None = Depends(get_optional_user),
):
    """比赛详情：题目列表（携带每题时限信息）
    可见性只看比赛本身：能进比赛的人，比赛内题目全部可见（私有题也不例外）"""
    out = _contest_out(c)
    cps = await db.scalars(
        select(ContestProblem).where(ContestProblem.contest_id == contest_id)
        .order_by(ContestProblem.alias))
    problems_out = []
    for cp in cps:
        p = await db.get(Problem, cp.problem_id)
        problems_out.append({
            "alias": cp.alias, "problem_id": cp.problem_id,
            "title": p.title if p else "",
            "time_limit_ms": p.config.get("time_limit_ms", 2000) if p else 2000,
            "memory_limit_mb": p.config.get("memory_limit_mb", 256) if p else 256,
            "visible": bool(p),
        })
    out["problems"] = problems_out
    return out


@router.post("/{contest_id}/register", status_code=201)
async def register_contest(
    contest_id: int, c: Contest = Depends(ContestAccess("view")),
    db: AsyncSession = Depends(get_db), user: User = CurrentUser,
):
    exists = await db.scalar(
        select(ContestParticipant).where(
            ContestParticipant.contest_id == contest_id,
            ContestParticipant.user_id == user.id))
    if exists:
        return {"ok": True, "already": True}
    db.add(ContestParticipant(contest_id=contest_id, user_id=user.id))
    await db.commit()
    return {"ok": True}


@router.get("/{contest_id}/standings")
async def standings(contest_id: int, c: Contest = Depends(ContestAccess("view")),
                    db: AsyncSession = Depends(get_db)):
    return await compute_standings(db, c)


@router.post("/{contest_id}/problems/{alias}/submit", response_model=dict, status_code=201)
async def contest_submit(
    contest_id: int, alias: str,
    c: Contest = Depends(ContestAccess("view")),
    body: dict = Body(...),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """比赛内提交：body 为 JSON {language, code}"""
    language = body.get("language", "python3.12")
    code = body.get("code", "")
    if not code.strip():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "代码不能为空")
    now = datetime.now(timezone.utc)
    if now < _aware(c.start_at) or now > _aware(c.end_at):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "比赛未在进行中")

    # 参赛校验
    participant = await db.scalar(
        select(ContestParticipant).where(
            ContestParticipant.contest_id == contest_id,
            ContestParticipant.user_id == user.id))
    if participant is None and user.role != UserRole.ADMIN:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "请先报名比赛")

    cp = await db.scalar(
        select(ContestProblem).where(
            ContestProblem.contest_id == contest_id,
            ContestProblem.alias == alias))
    if cp is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "题目不存在")
    p = await db.get(Problem, cp.problem_id)

    # 测试点列表：优先 testcases 表（上传数据时已同步）；无记录时回退读本地 manifest
    tcs = (await db.scalars(
        select(Testcase).where(Testcase.problem_id == p.id).order_by(Testcase.idx))).all()
    if tcs:
        case_list = [(tc.case_id, tc.score) for tc in tcs]
    else:
        from app.services.problem_data import data_dir
        data_version = p.config.get("data_version", "v1")
        manifest_path = data_dir(str(p.id), data_version) / "manifest.json"
        manifest = json.loads(manifest_path.read_bytes())
        case_list = [(c["id"], c.get("score", 0)) for c in manifest["cases"]]
    if not case_list:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "题目暂无测试数据")
    total_score = sum(score for _, score in case_list) or 100

    sub = Submission(
        user_id=user.id, problem_id=p.id, contest_id=contest_id,
        language=language, code_key=f"submissions/{p.id}-{user.id}",
        code=code,  # 源码留存，支持后台重判
        status=SubmissionStatus.WAITING,
    )
    db.add(sub)
    await db.flush()

    data_version = p.config.get("data_version", "v1")
    job = judge_pb2.SubmitJob(
        submission_id=str(sub.id), language=language, code=code.encode(),
        limits=judge_pb2.ResourceLimits(
            time_limit_ms=p.config.get("time_limit_ms", 2000),
            memory_limit_mb=p.config.get("memory_limit_mb", 256)),
        problem_id=str(p.id), data_version=data_version,
        cases=[judge_pb2.TestCase(test_case_id=cid, score=total_score // len(case_list))
               for cid, _ in case_list],
        stop_on_failure=(c.rule == ContestRule.ACM),
    )
    gw = get_gateway()
    result = await gw.submit(job, timeout=120)

    sub.status = NODE_STATUS_MAP.get(result.status, SubmissionStatus.SYSTEM_ERROR)
    sub.score = result.score
    sub.time_ms = result.time_used_ms
    sub.memory_kb = result.memory_used_kb
    sub.detail = {"cases": [{"idx": i, "status": cs.status}
                            for i, cs in enumerate(result.cases)],
                  "error_message": result.error_message}
    await db.commit()
    out = _to_out(sub)
    # 比赛进行中不透露具体哪个测试点错了（防打表）
    return {**out.model_dump(), "detail": []}
