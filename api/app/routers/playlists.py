"""题单路由：创建 / 列表 / 详情 / 编辑题目 / 进度

题单区分公有/私有，归属个人或团队，复用统一权限层。
"""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.database import get_db
from app.models import (
    OwnerType,
    Playlist,
    PlaylistProblem,
    Problem,
    Submission,
    SubmissionStatus,
    TeamMember,
    User,
    UserRole,
)
from app.services.access import require_team_manage
from app.services.access_deps import PlaylistAccess
from app.services.auth import CurrentUser, get_optional_user

router = APIRouter(prefix="/playlists", tags=["playlists"])


class PlaylistCreate(BaseModel):
    title: str = Field(min_length=1, max_length=128)
    description: str = ""
    is_public: bool = False
    owner_type: OwnerType = OwnerType.USER
    team_id: int | None = None


class PlaylistUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=128)
    description: str | None = None
    is_public: bool | None = None


def _out(pl: Playlist) -> dict:
    return {
        "id": pl.id, "title": pl.title, "description": pl.description,
        "is_public": pl.is_public, "owner_type": pl.owner_type.value,
        "owner_id": pl.owner_id, "created_at": pl.created_at.isoformat(),
    }


async def _resolve_owner(db: AsyncSession, req: PlaylistCreate, user: User) -> int:
    """校验归属，返回 owner_id"""
    if req.owner_type == OwnerType.TEAM:
        if not req.team_id:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "缺少 team_id")
        from app.models import Team
        t = await db.get(Team, req.team_id)
        if t is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "团队不存在")
        await require_team_manage(db, req.team_id, user)
        return req.team_id
    return user.id


@router.post("", status_code=201)
async def create_playlist(
    req: PlaylistCreate, db: AsyncSession = Depends(get_db), user: User = CurrentUser,
):
    pl = Playlist(
        title=req.title, description=req.description, is_public=req.is_public,
        owner_type=req.owner_type, owner_id=await _resolve_owner(db, req, user),
    )
    db.add(pl)
    await db.commit()
    await db.refresh(pl)
    return _out(pl)


@router.get("")
async def list_playlists(
    db: AsyncSession = Depends(get_db),
    user: User | None = Depends(get_optional_user),
):
    """可见题单列表（公有 + 我的 + 团队的）"""
    if user is None:
        stmt = select(Playlist).where(Playlist.is_public == True)  # noqa: E712
    elif user.role == UserRole.ADMIN:
        stmt = select(Playlist)
    else:
        my_team_ids = select(TeamMember.team_id).where(TeamMember.user_id == user.id)
        stmt = select(Playlist).where(
            (Playlist.is_public == True)  # noqa: E712
            | ((Playlist.owner_type == OwnerType.USER) & (Playlist.owner_id == user.id))
            | ((Playlist.owner_type == OwnerType.TEAM) & Playlist.owner_id.in_(my_team_ids)))
    rows = await db.scalars(stmt.order_by(Playlist.id.desc()).limit(100))
    return [_out(pl) for pl in rows]


@router.get("/{playlist_id}")
async def playlist_detail(
    playlist_id: int, pl: Playlist = Depends(PlaylistAccess("view")),
    db: AsyncSession = Depends(get_db),
    user: User | None = Depends(get_optional_user),
):
    """题单详情：题目列表 + 我的进度
    可见性只看题单本身：能进题单的人，题单内题目全部可见（私有题也不例外）"""
    rows = await db.scalars(
        select(PlaylistProblem).where(PlaylistProblem.playlist_id == pl.id)
        .order_by(PlaylistProblem.idx)
        .options(joinedload(PlaylistProblem.problem)))
    items = []
    for r in rows:
        p = r.problem
        items.append({
            "problem_id": p.id, "display_id": p.display_id, "title": p.title,
            "difficulty": p.difficulty, "visible": True,
        })
    # 我的进度：该用户对这些题目的首次 AC
    progress = []
    if user is not None:
        pids = [it["problem_id"] for it in items]
        if pids:
            acs = await db.scalars(
                select(Submission.problem_id).where(
                    Submission.user_id == user.id,
                    Submission.status == SubmissionStatus.ACCEPTED,
                    Submission.problem_id.in_(pids)).distinct())
            progress = list(acs)
    return {**_out(pl), "problems": items, "solved_problem_ids": progress}


@router.put("/{playlist_id}")
async def update_playlist(
    playlist_id: int, req: PlaylistUpdate,
    pl: Playlist = Depends(PlaylistAccess("manage")),
    db: AsyncSession = Depends(get_db),
):
    if req.title is not None:
        pl.title = req.title
    if req.description is not None:
        pl.description = req.description
    if req.is_public is not None:
        pl.is_public = req.is_public
    await db.commit()
    return _out(pl)


@router.delete("/{playlist_id}")
async def delete_playlist(
    playlist_id: int,
    pl: Playlist = Depends(PlaylistAccess("manage")),
    db: AsyncSession = Depends(get_db),
):
    """删除题单（仅管理者）。playlist_problems 关联行由 FK CASCADE 级联清除，
    题目本身不受影响。不可恢复。"""
    await db.delete(pl)
    await db.commit()
    return {"ok": True}


@router.put("/{playlist_id}/problems", status_code=201)
async def set_playlist_problems(
    playlist_id: int, body: dict,
    pl: Playlist = Depends(PlaylistAccess("manage")),
    db: AsyncSession = Depends(get_db),
    user: User = CurrentUser,
):
    """整体设置题单题目：body {"problem_ids": [3, 7, ...]} 按顺序
    可加「我可见」的任意题目（含自己的私有题）；他人私有题不可加（防借题单泄露）"""
    from app.services.access import can_view

    # ID 可能以 JSON 字符串传入（前端大整数防精度丢失统一转字符串），先归一为 int
    raw_ids = body.get("problem_ids", [])
    problem_ids = [int(pid) for pid in raw_ids]
    seen = set()
    for pid in problem_ids:
        if pid in seen:
            continue
        seen.add(pid)
        p = await db.get(Problem, pid)
        if p is None:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"题目 {pid} 不存在")
        if not await can_view(db, user, p.owner_type, p.owner_id, p.is_public):
            raise HTTPException(
                status.HTTP_403_FORBIDDEN, f"题目 {p.display_id} 为他人私有题目，无法添加")
    old = await db.scalars(
        select(PlaylistProblem).where(PlaylistProblem.playlist_id == pl.id))
    for r in old:
        await db.delete(r)
    # 先 flush 落库 DELETE：SQLAlchemy flush 时 INSERT 先于 DELETE 执行，
    # 不提前 flush 会撞 uq_playlist_problem 唯一约束（重复保存同一批题目必现 500）
    await db.flush()
    for i, pid in enumerate(problem_ids):
        db.add(PlaylistProblem(playlist_id=pl.id, problem_id=pid, idx=i))
    await db.commit()
    return {"ok": True, "count": len(problem_ids)}
