"""比赛路由：创建/列表/详情/报名/比赛题目/提交/榜单/归档/重现赛(VP)

归档规则：比赛结束满 24 小时后自动归档（派生状态，不落库）。
归档后的比赛：仍可提交练习、可创建重现赛（VP），但不能再编辑比赛信息。
比赛分类：未结束（含未开始/进行中/结束未满 24h）与 已结束（已归档）两类。
"""

import json
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Body, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import (
    Contest,
    ContestAnnouncement,
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
from app.services.access import can_manage, require_team_manage
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


# 归档宽限期：结束满 24h 自动归档（派生状态，改 end_at 即随之变化，无需落库/迁移）
ARCHIVE_AFTER_END = timedelta(hours=24)


def _is_archived(c: Contest, now: datetime) -> bool:
    return now > _aware(c.end_at) + ARCHIVE_AFTER_END


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
        "archived": _is_archived(c, now),
        "start_at": c.start_at.isoformat(), "end_at": c.end_at.isoformat(),
        "board_freeze_minutes": c.board_freeze_minutes,
        "description": c.description,
        "is_public": c.is_public,
        "owner_type": c.owner_type.value,
        "owner_id": c.owner_id,
    }


async def _is_manageable(db: AsyncSession, user: User | None, c: Contest) -> bool:
    """当前用户能否管理该比赛（未登录一律不可）"""
    if user is None:
        return False
    return await can_manage(db, user, c.owner_type, c.owner_id)


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
    out["is_manageable"] = await _is_manageable(db, user, c)
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


class ContestVpCreate(BaseModel):
    """重现赛（VP）参数：时间窗缺省为「立即开始、时长与原赛相同」"""
    title: str | None = Field(default=None, max_length=128)
    start_at: datetime | None = None
    end_at: datetime | None = None
    is_public: bool = False


@router.post("/{contest_id}/vp", status_code=201)
async def create_virtual_replay(
    contest_id: int,
    req: ContestVpCreate,
    c: Contest = Depends(ContestAccess("view")),
    db: AsyncSession = Depends(get_db),
    user: User = CurrentUser,
):
    """创建重现赛（VP）：复制原比赛的题目与基本信息，新建一场归属自己的比赛。
    原比赛（含已归档）任何阶段都可 VP；新赛默认私有、不封榜，创建者自动报名。"""
    now = datetime.now(timezone.utc)
    duration = _aware(c.end_at) - _aware(c.start_at)
    start = _aware(req.start_at) if req.start_at else now
    end = _aware(req.end_at) if req.end_at else start + duration
    if end <= start:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "结束时间必须晚于开始时间")
    nc = Contest(
        title=(req.title or f"{c.title}（重现赛）")[:128],
        description=c.description, rule=c.rule,
        start_at=start, end_at=end,
        board_freeze_minutes=0,  # VP 重新计时，不沿用原封榜
        is_public=req.is_public, owner_type=OwnerType.USER, owner_id=user.id,
    )
    db.add(nc)
    await db.flush()
    cps = (await db.scalars(
        select(ContestProblem).where(ContestProblem.contest_id == contest_id)
        .order_by(ContestProblem.alias))).all()
    for cp in cps:
        db.add(ContestProblem(contest_id=nc.id, problem_id=cp.problem_id,
                              alias=cp.alias))
    db.add(ContestParticipant(contest_id=nc.id, user_id=user.id))
    await db.commit()
    return {**_contest_out(nc), "vp_of": c.id, "problems": len(cps)}


@router.get("/{contest_id}/standings")
async def standings(contest_id: int, c: Contest = Depends(ContestAccess("view")),
                    db: AsyncSession = Depends(get_db)):
    return await compute_standings(db, c)


# ---------- 比赛内提交记录 ----------

@router.get("/{contest_id}/submissions")
async def contest_submissions(
    contest_id: int,
    problem_alias: str | None = None,
    username: str | None = None,
    page: int = 1,
    page_size: int = 20,
    c: Contest = Depends(ContestAccess("view")),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """比赛内提交记录：管理者和 ADMIN 可看所有人的，其他用户只能看自己的"""
    manageable = await _is_manageable(db, user, c)
    if not manageable and user.role != UserRole.ADMIN:
        # 非管理者：强制只看自己的（username 参数仅管理者可用）
        stmt = select(Submission).where(
            Submission.contest_id == contest_id,
            Submission.user_id == user.id)
    else:
        stmt = select(Submission).where(Submission.contest_id == contest_id)
        if username:
            # 管理者按用户名筛选：先定位用户，不存在则直接返回空
            target = await db.scalar(select(User).where(User.username == username))
            if target is None:
                return {"total": 0, "items": [], "can_view_all": True}
            stmt = stmt.where(Submission.user_id == target.id)

    if problem_alias:
        cp = await db.scalar(
            select(ContestProblem).where(
                ContestProblem.contest_id == contest_id,
                ContestProblem.alias == problem_alias))
        if cp is None:
            return {"total": 0, "items": [], "can_view_all": manageable}
        stmt = stmt.where(Submission.problem_id == cp.problem_id)

    total = await db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = list(await db.scalars(
        stmt.order_by(Submission.id.desc())
        .offset((page - 1) * page_size).limit(page_size)))

    users = {u.id: u.username for u in await db.scalars(
        select(User).where(User.id.in_({s.user_id for s in rows} or {0})))}
    aliases = {cp.problem_id: cp.alias for cp in await db.scalars(
        select(ContestProblem).where(ContestProblem.contest_id == contest_id))}
    items = []
    for s in rows:
        out = _to_out(s)
        items.append({
            **out.model_dump(),
            "username": users.get(s.user_id, "?"),
            "problem_alias": aliases.get(s.problem_id, "?"),
            # 非管理者隐藏测试点细节（防打表）；管理者/ADMIN 可看
            "detail": s.detail.get("cases", []) if manageable else [],
        })
    return {"total": total or 0, "items": items, "can_view_all": manageable}


@router.get("/{contest_id}/submissions/{submission_id}")
async def contest_submission_detail(
    contest_id: int, submission_id: int,
    c: Contest = Depends(ContestAccess("view")),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """比赛内提交详情（源码/测试点明细）
    可见范围与列表一致：本人/比赛管理者/ADMIN，其余 404。
    - 源码：本人与管理者随时可见
    - 测试点明细与错误信息：管理者随时可见；本人仅比赛结束后可见
      （进行中隐藏防打表；编译错误信息不含测试数据，对本人始终可见）"""
    sub = await db.get(Submission, submission_id)
    if sub is None or sub.contest_id != contest_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "提交不存在")
    manageable = await _is_manageable(db, user, c)
    if not (sub.user_id == user.id or manageable):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "提交不存在")

    d = sub.detail or {}
    full = manageable or _aware(c.end_at) <= datetime.now(timezone.utc)
    if full or sub.status == SubmissionStatus.COMPILE_ERROR:
        error_message = d.get("error_message", "")
    else:
        error_message = ""
    owner = await db.get(User, sub.user_id)
    cp = await db.scalar(select(ContestProblem).where(
        ContestProblem.contest_id == contest_id,
        ContestProblem.problem_id == sub.problem_id))
    return {
        **_to_out(sub).model_dump(),
        "username": owner.username if owner else "?",
        "problem_alias": cp.alias if cp else "?",
        "code": sub.code,  # 旧提交可能为 None（未留存源码）
        "detail": d.get("cases", []) if full else [],
        "error_message": error_message,
    }


@router.post("/{contest_id}/problems/{alias}/submit", response_model=dict, status_code=201)
async def contest_submit(
    contest_id: int, alias: str,
    c: Contest = Depends(ContestAccess("view")),
    body: dict = Body(...),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """比赛内提交：body 为 JSON {language, code}
    时间窗：开始后均可提交；结束后/归档后作为练习继续开放（规则见模块头注释）。
    注意：结束后提交也会计入榜单重放（现有榜单语义），练习提交请知悉。"""
    language = body.get("language", "python3.12")
    code = body.get("code", "")
    if not code.strip():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "代码不能为空")
    now = datetime.now(timezone.utc)
    if now < _aware(c.start_at):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "比赛尚未开始")

    # 参赛校验：进行中的比赛必须报名；已结束/已归档属于练习提交，对可见者开放
    if now <= _aware(c.end_at):
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

    # 测试点列表：优先 testcases 表（上传数据时已同步）；无记录时回退读 manifest
    tcs = (await db.scalars(
        select(Testcase).where(Testcase.problem_id == p.id).order_by(Testcase.idx))).all()
    case_list = [(tc.case_id, tc.score) for tc in tcs]
    if not case_list:
        from app.services.problem_data import read_manifest
        manifest = await read_manifest(
            str(p.id), p.config.get("data_version", "v1")) or {"cases": []}
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


# ---------- 比赛管理（创建者/团队管理员/ADMIN） ----------

class ContestUpdate(BaseModel):
    """比赛信息编辑：归档（结束满 24h）前可改时间与封榜"""
    start_at: datetime | None = None
    end_at: datetime | None = None
    board_freeze_minutes: int | None = Field(default=None, ge=0)


@router.patch("/{contest_id}")
async def update_contest(
    contest_id: int,
    req: ContestUpdate,
    c: Contest = Depends(ContestAccess("manage")),
    db: AsyncSession = Depends(get_db),
):
    """编辑比赛时间：归档（结束满 24h）前可改；结束时间必须晚于开始时间"""
    if _is_archived(c, datetime.now(timezone.utc)):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "比赛已归档（结束后满 24 小时），不能再编辑")
    start = _aware(req.start_at) if req.start_at is not None else _aware(c.start_at)
    end = _aware(req.end_at) if req.end_at is not None else _aware(c.end_at)
    if end <= start:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "结束时间必须晚于开始时间")
    if req.start_at is not None:
        c.start_at = req.start_at
    if req.end_at is not None:
        c.end_at = req.end_at
    if req.board_freeze_minutes is not None:
        c.board_freeze_minutes = req.board_freeze_minutes
    await db.commit()
    return _contest_out(c)


# ---------- 比赛公告 ----------

def _ann_out(a: ContestAnnouncement, author_name: str = "") -> dict:
    return {
        "id": a.id, "contest_id": a.contest_id,
        "title": a.title, "content": a.content,
        "author_id": a.author_id, "author_name": author_name,
        "created_at": a.created_at.isoformat() if a.created_at else "",
    }


@router.get("/{contest_id}/announcements")
async def list_contest_announcements(
    contest_id: int,
    c: Contest = Depends(ContestAccess("view")),
    db: AsyncSession = Depends(get_db),
):
    """比赛公告列表（能看比赛的人都能看；按时间倒序）"""
    rows = (await db.scalars(
        select(ContestAnnouncement)
        .where(ContestAnnouncement.contest_id == contest_id)
        .order_by(ContestAnnouncement.created_at.desc()))).all()
    users = {u.id: u.username for u in await db.scalars(
        select(User).where(User.id.in_({a.author_id for a in rows} or {0})))}
    return [_ann_out(a, users.get(a.author_id, "?")) for a in rows]


class ContestAnnouncementCreate(BaseModel):
    title: str = Field(min_length=1, max_length=128)
    content: str = Field(default="", max_length=10_000)


@router.post("/{contest_id}/announcements", status_code=201)
async def create_contest_announcement(
    contest_id: int,
    req: ContestAnnouncementCreate,
    c: Contest = Depends(ContestAccess("manage")),
    db: AsyncSession = Depends(get_db),
    user: User = CurrentUser,
):
    """发布公告：仅比赛管理者（创建者/团队管理员/ADMIN）"""
    a = ContestAnnouncement(
        contest_id=contest_id, title=req.title, content=req.content, author_id=user.id)
    db.add(a)
    await db.commit()
    return _ann_out(a, user.username)


# ---------- 按题目批量重测 ----------

@router.post("/{contest_id}/problems/{alias}/rejudge")
async def rejudge_contest_problem(
    contest_id: int, alias: str,
    c: Contest = Depends(ContestAccess("manage")),
    db: AsyncSession = Depends(get_db),
):
    """批量重测该题在比赛内的全部提交（仅比赛结束前；源码留存的提交才可重测）"""
    if _aware(c.end_at) <= datetime.now(timezone.utc):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "比赛已结束，不能再重测")

    cp = await db.scalar(
        select(ContestProblem).where(
            ContestProblem.contest_id == contest_id,
            ContestProblem.alias == alias))
    if cp is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "题目不存在")
    p = await db.get(Problem, cp.problem_id)
    if p is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "题目已删除")

    subs = list(await db.scalars(
        select(Submission)
        .where(Submission.contest_id == contest_id,
               Submission.problem_id == p.id)
        .order_by(Submission.id)))
    skippable = [s for s in subs if not s.code]
    targets = [s for s in subs if s.code]
    if not targets:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"该题共 {len(subs)} 条提交，均未留存源码，无法重测")

    # 测试点列表：优先 testcases 表（上传数据时已同步）；无记录时回退读 manifest
    tcs = (await db.scalars(
        select(Testcase).where(Testcase.problem_id == p.id).order_by(Testcase.idx))).all()
    case_list = [(tc.case_id, tc.score) for tc in tcs]
    if not case_list:
        from app.services.problem_data import read_manifest
        manifest = await read_manifest(
            str(p.id), p.config.get("data_version", "v1"))
        case_list = [(c["id"], c.get("score", 0)) for c in (manifest or {}).get("cases", [])]
    if not case_list:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "题目暂无测试数据")

    total_score = sum(score for _, score in case_list)
    data_version = p.config.get("data_version", "v1")
    stop_on_failure = (c.rule == ContestRule.ACM)
    gw = get_gateway()

    ok, fail = 0, 0
    last_label = ""
    for s in targets:
        s.status = SubmissionStatus.WAITING
        job = judge_pb2.SubmitJob(
            submission_id=str(s.id), language=s.language, code=s.code.encode(),
            limits=judge_pb2.ResourceLimits(
                time_limit_ms=p.config.get("time_limit_ms", 2000),
                memory_limit_mb=p.config.get("memory_limit_mb", 256)),
            problem_id=str(p.id), data_version=data_version,
            cases=[judge_pb2.TestCase(test_case_id=cid, score=total_score // len(case_list))
                   for cid, _ in case_list],
            stop_on_failure=stop_on_failure,
        )
        try:
            result = await gw.submit(job, timeout=120)
        except Exception:  # noqa: BLE001 单条失败不中断整批
            s.status = SubmissionStatus.SYSTEM_ERROR
            fail += 1
            await db.commit()
            continue
        s.status = NODE_STATUS_MAP.get(result.status, SubmissionStatus.SYSTEM_ERROR)
        s.score = result.score
        s.time_ms = result.time_used_ms
        s.memory_kb = result.memory_used_kb
        s.detail = {
            "cases": [{"idx": i, "status": cs.status,
                       "time_used_ms": cs.time_used_ms, "memory_used_kb": cs.memory_used_kb}
                      for i, cs in enumerate(result.cases)],
            "error_message": result.error_message,
        }
        last_label = STATUS_LABEL[s.status.value]
        ok += 1
        await db.commit()

    return {"ok": True, "total": len(subs), "rejudged": ok,
            "skipped": len(skippable), "failed": fail, "last_status": last_label}
