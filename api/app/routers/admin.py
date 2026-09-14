# =============================================================
# 文件: api/app/routers/admin.py
# 用途: 管理后台路由组（/admin/*），整组挂 require_admin 强校验
#       包含站点概况、用户/题目/比赛/题单/团队/提交管理、判题节点监控、单条重判
# =============================================================

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.judge_gateway.gen.judge.v1 import judge_pb2
from app.judge_gateway.server import get_gateway
from app.models import (
    CheckIn,
    Contest,
    Playlist,
    Problem,
    Submission,
    SubmissionStatus,
    Tag,
    Team,
    Testcase,
    User,
    UserRole,
)
from app.routers.submissions import NODE_STATUS_MAP, STATUS_LABEL
from app.services.auth import require_admin

router = APIRouter(prefix="/admin", tags=["admin"],
                   dependencies=[Depends(require_admin)])


# ---------- 站点概况 ----------

@router.get("/overview")
async def overview(db: AsyncSession = Depends(get_db)):
    """Dashboard 统计卡：用户数 / 今日提交 / 今日打卡 / 题目数 / 等待队列"""
    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    today_str = now.strftime("%Y-%m-%d")

    total_users = await db.scalar(select(func.count(User.id)))
    total_problems = await db.scalar(select(func.count(Problem.id)))
    total_submissions = await db.scalar(select(func.count(Submission.id)))
    today_submissions = await db.scalar(
        select(func.count(Submission.id)).where(Submission.submitted_at >= today_start))
    waiting = await db.scalar(
        select(func.count(Submission.id)).where(
            Submission.status.in_([SubmissionStatus.WAITING, SubmissionStatus.JUDGING])))
    total_teams = await db.scalar(select(func.count(Team.id)))
    total_contests = await db.scalar(select(func.count(Contest.id)))
    today_checkins = await db.scalar(
        select(func.count(CheckIn.id)).where(CheckIn.day == today_str))
    online_nodes = await get_gateway().node_count()

    return {
        "users": total_users or 0,
        "problems": total_problems or 0,
        "submissions": total_submissions or 0,
        "today_submissions": today_submissions or 0,
        "today_checkins": today_checkins or 0,
        "waiting": waiting or 0,
        "teams": total_teams or 0,
        "contests": total_contests or 0,
        "online_nodes": online_nodes,
    }


# ---------- 用户管理 ----------

def _user_to_admin_out(u: User) -> dict:
    return {
        "id": u.id, "username": u.username, "email": u.email,
        "role": u.role.value, "rating": u.rating, "banned": u.banned,
        "created_at": u.created_at.isoformat() if u.created_at else "",
    }


class RoleUpdate(BaseModel):
    role: str = Field(pattern="^(user|admin)$")


class BanUpdate(BaseModel):
    banned: bool


@router.get("/users")
async def list_users(
    q: str = "",
    page: int = 1,
    page_size: int = 20,
    db: AsyncSession = Depends(get_db),
):
    """用户列表（分页 + 用户名/邮箱搜索）"""
    stmt = select(User)
    if q:
        stmt = stmt.where(User.username.ilike(f"%{q}%") | User.email.ilike(f"%{q}%"))
    total = await db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = await db.scalars(
        stmt.order_by(User.id).offset((page - 1) * page_size).limit(page_size))
    items = [_user_to_admin_out(u) for u in rows]
    return {"total": total or 0, "items": items}


@router.put("/users/{user_id}/role")
async def update_role(
    user_id: int,
    body: RoleUpdate,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    if user_id == admin.id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "不能修改自己的角色")
    u = await db.get(User, user_id)
    if u is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "用户不存在")
    u.role = UserRole(body.role)
    await db.commit()
    return {"ok": True, "role": u.role.value}


@router.put("/users/{user_id}/ban")
async def ban_user(
    user_id: int,
    body: BanUpdate,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    if user_id == admin.id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "不能封禁自己")
    u = await db.get(User, user_id)
    if u is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "用户不存在")
    u.banned = body.banned
    await db.commit()
    return {"ok": True, "banned": u.banned}


# ---------- 题目管理（全量，含私有） ----------

@router.get("/problems")
async def list_problems(
    q: str = "",
    db: AsyncSession = Depends(get_db),
):
    """全量题目列表：含私有，带归属/数据版本/测试点数"""
    stmt = select(Problem)
    if q:
        stmt = stmt.where(Problem.title.ilike(f"%{q}%"))
    rows = await db.scalars(stmt.order_by(Problem.id).limit(200))
    items = []
    for p in rows:
        case_count = await db.scalar(
            select(func.count(Testcase.id)).where(Testcase.problem_id == p.id))
        items.append({
            "id": p.id, "display_id": p.display_id, "title": p.title,
            "difficulty": p.difficulty, "is_public": p.is_public,
            "owner_type": p.owner_type.value, "owner_id": p.owner_id,
            "data_version": p.config.get("data_version", "v1"),
            "case_count": case_count or 0,
        })
    return {"items": items}


class ProblemUpdate(BaseModel):
    is_public: bool | None = None
    title: str | None = Field(default=None, max_length=128)


@router.put("/problems/{problem_id}")
async def update_problem(
    problem_id: int,
    body: ProblemUpdate,
    db: AsyncSession = Depends(get_db),
):
    p = await db.get(Problem, problem_id)
    if p is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "题目不存在")
    if body.title is not None:
        p.title = body.title
    if body.is_public is not None:
        p.is_public = body.is_public
    await db.commit()
    return {"ok": True, "is_public": p.is_public}


# ---------- 标签管理 ----------

async def _tag_usage_counts(db: AsyncSession) -> dict[str, int]:
    """统计每个标签名被多少道题目使用（含私有题，后台视角看全量）"""
    rows = await db.scalars(select(Problem.tags))
    counter: dict[str, int] = {}
    for tags in rows:
        for t in set(tags or []):
            if isinstance(t, str) and t:
                counter[t] = counter.get(t, 0) + 1
    return counter


async def _replace_tag_name(db: AsyncSession, old: str, new: str | None) -> int:
    """把所有题目 tags 数组里的 old 名替换为 new（new=None 表示移除该名），返回涉及题数"""
    rows = await db.scalars(select(Problem).where(Problem.tags.isnot(None)))
    touched = 0
    for p in rows:
        tags = list(p.tags or [])
        if old not in tags:
            continue
        if new is None:
            tags = [t for t in tags if t != old]
        else:
            tags = [new if t == old else t for t in tags]
            # 重命名后同题内可能撞名，去重保持数组语义
            tags = list(dict.fromkeys(tags))
        p.tags = tags
        touched += 1
    return touched


@router.get("/tags")
async def list_tags(
    q: str = "",
    db: AsyncSession = Depends(get_db),
):
    """全量标签实例列表（含未被题目引用的孤儿标签），带使用题数"""
    stmt = select(Tag)
    if q:
        stmt = stmt.where(Tag.name.ilike(f"%{q}%"))
    rows = await db.scalars(stmt.order_by(Tag.name))
    counts = await _tag_usage_counts(db)
    items = [{
        "id": t.id, "name": t.name,
        "problem_count": counts.get(t.name, 0),
        "created_at": t.created_at.isoformat() if t.created_at else "",
    } for t in rows]
    return {"items": items}


class TagRename(BaseModel):
    name: str = Field(min_length=1, max_length=32)


@router.post("/tags", status_code=201)
async def create_tag_admin(
    body: TagRename,
    db: AsyncSession = Depends(get_db),
):
    """后台新建标签实例（重名 400，与前台出题弹窗的幂等创建不同：管理端应显式感知冲突）"""
    name = body.name.strip()
    dup = await db.scalar(select(Tag).where(Tag.name == name))
    if dup is not None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"标签「{name}」已存在")
    tag = Tag(name=name)
    db.add(tag)
    await db.commit()
    await db.refresh(tag)
    return {"id": tag.id, "name": tag.name,
            "problem_count": 0,
            "created_at": tag.created_at.isoformat() if tag.created_at else ""}


@router.put("/tags/{tag_id}")
async def rename_tag(
    tag_id: int,
    body: TagRename,
    db: AsyncSession = Depends(get_db),
):
    """重命名标签：同步替换所有题目 tags 数组中的旧名（题面引用随动）"""
    name = body.name.strip()
    tag = await db.get(Tag, tag_id)
    if tag is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "标签不存在")
    if name == tag.name:
        return {"ok": True, "name": tag.name, "touched": 0}
    dup = await db.scalar(select(Tag).where(Tag.name == name))
    if dup is not None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"标签「{name}」已存在")
    old = tag.name
    tag.name = name
    touched = await _replace_tag_name(db, old, name)
    await db.commit()
    return {"ok": True, "name": name, "touched": touched}


@router.delete("/tags/{tag_id}")
async def delete_tag(
    tag_id: int,
    db: AsyncSession = Depends(get_db),
):
    """删除标签实例：同时从所有题目 tags 数组移除该名（题目本身不受影响）"""
    tag = await db.get(Tag, tag_id)
    if tag is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "标签不存在")
    touched = await _replace_tag_name(db, tag.name, None)
    await db.delete(tag)
    await db.commit()
    return {"ok": True, "touched": touched}


# ---------- 比赛管理 ----------

@router.get("/contests")
async def list_contests(db: AsyncSession = Depends(get_db)):
    rows = await db.scalars(select(Contest).order_by(Contest.id.desc()).limit(200))
    return {"items": [{
        "id": c.id, "title": c.title, "rule": c.rule.value,
        "start_at": c.start_at.isoformat(), "end_at": c.end_at.isoformat(),
        "is_public": c.is_public, "owner_type": c.owner_type.value, "owner_id": c.owner_id,
    } for c in rows]}


# ---------- 题单管理 ----------

@router.get("/playlists")
async def list_playlists(db: AsyncSession = Depends(get_db)):
    rows = await db.scalars(select(Playlist).order_by(Playlist.id.desc()).limit(200))
    return {"items": [{
        "id": pl.id, "title": pl.title, "is_public": pl.is_public,
        "owner_type": pl.owner_type.value, "owner_id": pl.owner_id,
        "created_at": pl.created_at.isoformat(),
    } for pl in rows]}


# ---------- 团队管理 ----------

@router.get("/teams")
async def list_teams(db: AsyncSession = Depends(get_db)):
    rows = await db.scalars(select(Team).order_by(Team.id.desc()).limit(200))
    items = []
    for t in rows:
        member_count = await db.scalar(
            select(func.count()).select_from(
                select(Team.id).where(Team.id == t.id).subquery()))
        owner = await db.get(User, t.owner_id)
        items.append({
            "id": t.id, "name": t.name, "description": t.description,
            "owner_id": t.owner_id, "owner_name": owner.username if owner else "?",
            "member_count": member_count or 0,
            "created_at": t.created_at.isoformat(),
        })
    return {"items": items}


# ---------- 提交管理 ----------

class AdminSubmissionOut(BaseModel):
    id: int
    user_id: int
    problem_id: int
    contest_id: int | None
    language: str
    status: str
    status_label: str
    score: int
    time_ms: int
    memory_kb: int
    submitted_at: str
    has_code: bool


@router.get("/submissions")
async def list_submissions(
    page: int = 1,
    page_size: int = 30,
    problem_id: int | None = None,
    user_id: int | None = None,
    status_q: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    """全站提交流水（分页 + 筛选），带用户名/题目标题"""
    stmt = select(Submission)
    if problem_id:
        stmt = stmt.where(Submission.problem_id == problem_id)
    if user_id:
        stmt = stmt.where(Submission.user_id == user_id)
    if status_q:
        try:
            stmt = stmt.where(Submission.status == SubmissionStatus(status_q))
        except ValueError:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "无效的状态值")
    total = await db.scalar(select(func.count()).select_from(stmt.subquery()))
    # 注意：ScalarResult 一次性迭代，先物化成 list 再多次使用
    rows = list(await db.scalars(
        stmt.order_by(Submission.id.desc())
        .offset((page - 1) * page_size).limit(page_size)))
    users = {u.id: u.username for u in await db.scalars(
        select(User).where(User.id.in_({s.user_id for s in rows} or {0})))}
    problems = {p.id: p.title for p in await db.scalars(
        select(Problem).where(Problem.id.in_({s.problem_id for s in rows} or {0})))}
    items = []
    for s in rows:
        items.append({
            "id": s.id, "user_id": s.user_id, "username": users.get(s.user_id, "?"),
            "problem_id": s.problem_id, "problem_title": problems.get(s.problem_id, "?"),
            "contest_id": s.contest_id, "language": s.language,
            "status": s.status.value, "status_label": STATUS_LABEL[s.status.value],
            "score": s.score, "time_ms": s.time_ms, "memory_kb": s.memory_kb,
            "submitted_at": s.submitted_at.isoformat(),
            "has_code": bool(s.code),
        })
    return {"total": total or 0, "items": items}


@router.get("/submissions/{submission_id}")
async def submission_admin_detail(
    submission_id: int,
    db: AsyncSession = Depends(get_db),
):
    """后台提交详情：含源码与完整判题细节"""
    s = await db.get(Submission, submission_id)
    if s is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "提交不存在")
    detail = s.detail or {}
    return {
        "id": s.id, "user_id": s.user_id, "problem_id": s.problem_id,
        "contest_id": s.contest_id, "language": s.language,
        "status": s.status.value, "status_label": STATUS_LABEL[s.status.value],
        "score": s.score, "time_ms": s.time_ms, "memory_kb": s.memory_kb,
        "submitted_at": s.submitted_at.isoformat(),
        "code": s.code,  # 旧提交可能为 NULL
        "detail": detail.get("cases", []),
        "error_message": detail.get("error_message", ""),
    }


@router.post("/submissions/{submission_id}/rejudge")
async def rejudge_submission(
    submission_id: int,
    db: AsyncSession = Depends(get_db),
):
    """单条重判：用留存的源码重新组装 SubmitJob，覆盖结果字段"""
    s = await db.get(Submission, submission_id)
    if s is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "提交不存在")
    if not s.code:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "旧提交未留存源码，不支持重判")
    p = await db.get(Problem, s.problem_id)
    if p is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "题目已删除")

    testcases = await db.scalars(
        select(Testcase).where(Testcase.problem_id == p.id).order_by(Testcase.idx))
    tcs = list(testcases)
    if not tcs:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "题目暂无测试数据")

    s.status = SubmissionStatus.WAITING
    await db.commit()

    data_version = p.config.get("data_version", "v1")
    total_score = sum(tc.score for tc in tcs)
    job = judge_pb2.SubmitJob(
        submission_id=str(s.id),
        language=s.language,
        code=s.code.encode(),
        limits=judge_pb2.ResourceLimits(
            time_limit_ms=p.config.get("time_limit_ms", 2000),
            memory_limit_mb=p.config.get("memory_limit_mb", 256)),
        problem_id=str(p.id),
        data_version=data_version,
        cases=[judge_pb2.TestCase(test_case_id=tc.case_id, score=tc.score) for tc in tcs],
        stop_on_failure=True,
    )
    gw = get_gateway()
    try:
        result = await gw.submit(job, timeout=120)
    except Exception as e:  # noqa: BLE001 节点不可达等
        s.status = SubmissionStatus.SYSTEM_ERROR
        await db.commit()
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, f"重判失败: {e}") from e

    s.status = NODE_STATUS_MAP.get(result.status, SubmissionStatus.SYSTEM_ERROR)
    s.score = result.score
    s.time_ms = result.time_used_ms
    s.memory_kb = result.memory_used_kb
    s.detail = {
        "cases": [{"idx": i, "status": c.status,
                   "time_used_ms": c.time_used_ms, "memory_used_kb": c.memory_used_kb}
                  for i, c in enumerate(result.cases)],
        "error_message": result.error_message,
    }
    await db.commit()
    return {"ok": True, "status": s.status.value,
            "status_label": STATUS_LABEL[s.status.value], "score": s.score}


# ---------- 判题节点监控 ----------

@router.get("/judges")
async def judges(db: AsyncSession = Depends(get_db)):
    """节点状态聚合：网关快照（节点容量占用 + 等待队列）"""
    return get_gateway().snapshot()
