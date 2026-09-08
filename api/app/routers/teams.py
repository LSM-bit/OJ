"""团队路由：创建 / 详情 / 成员管理 / 邀请码 / 角色管理

角色：owner（队长，发起人）/ admin（副队长）/ member（队员）
加入方式：队长/副队生成邀请码，用户凭码加入（一期）
"""

import secrets

from fastapi import APIRouter, Body, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.database import get_db
from app.models import Team, TeamMember, TeamRole, User
from app.services.access import get_team_role, require_team_manage
from app.services.auth import CurrentUser, get_current_user, get_optional_user

router = APIRouter(prefix="/teams", tags=["teams"])

# 邀请码：明文 -> 团队 id（一期内存态，重启失效；二期入库）
_INVITE_CODES: dict[str, int] = {}


class TeamCreate(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    description: str = Field(default="", max_length=2000)


class TeamUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=64)
    description: str | None = Field(default=None, max_length=2000)


def _team_out(t: Team, member_count: int | None = None) -> dict:
    out = {
        "id": t.id, "name": t.name, "description": t.description,
        "owner_id": t.owner_id, "max_members": t.max_members,
        "created_at": t.created_at.isoformat(),
    }
    if member_count is not None:
        out["member_count"] = member_count
    return out


@router.post("", status_code=201)
async def create_team(
    req: TeamCreate, db: AsyncSession = Depends(get_db), user: User = CurrentUser,
):
    """创建团队，发起人自动成为队长"""
    exists = await db.scalar(select(Team).where(Team.name == req.name))
    if exists:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "团队名已存在")
    t = Team(name=req.name, description=req.description, owner_id=user.id)
    db.add(t)
    await db.flush()
    db.add(TeamMember(team_id=t.id, user_id=user.id, role=TeamRole.OWNER))
    await db.commit()
    await db.refresh(t)
    return _team_out(t, member_count=1)


@router.get("")
async def list_my_teams(db: AsyncSession = Depends(get_db), user: User = CurrentUser):
    """我加入的团队列表"""
    rows = await db.scalars(
        select(TeamMember).where(TeamMember.user_id == user.id)
        .options(joinedload(TeamMember.team)))
    return [
        {**_team_out(m.team), "my_role": m.role.value}
        for m in rows
    ]


@router.get("/{team_id}")
async def team_detail(
    team_id: int, db: AsyncSession = Depends(get_db), user: User | None = Depends(get_optional_user),
):
    t = await db.get(Team, team_id)
    if t is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "团队不存在")
    members = await db.scalars(
        select(TeamMember).where(TeamMember.team_id == team_id)
        .options(joinedload(TeamMember.user)))
    member_list = [
        {"user_id": m.user_id, "username": m.user.username, "role": m.role.value}
        for m in members
    ]
    my_role = await get_team_role(db, team_id, user.id) if user else None
    # 非成员只看成员数量，不看名单
    if my_role is None and (user is None or user.role.value != "admin"):
        return {**_team_out(t), "member_count": len(member_list)}
    return {**_team_out(t), "members": member_list, "my_role": my_role.value if my_role else None}


@router.put("/{team_id}")
async def update_team(
    team_id: int, req: TeamUpdate,
    db: AsyncSession = Depends(get_db), user: User = CurrentUser,
):
    t = await db.get(Team, team_id)
    if t is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "团队不存在")
    await require_team_manage(db, team_id, user)
    if req.name is not None:
        t.name = req.name
    if req.description is not None:
        t.description = req.description
    await db.commit()
    return _team_out(t)


@router.delete("/{team_id}")
async def delete_team(
    team_id: int, db: AsyncSession = Depends(get_db), user: User = CurrentUser,
):
    """解散团队（仅队长/ADMIN）"""
    t = await db.get(Team, team_id)
    if t is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "团队不存在")
    role = await get_team_role(db, team_id, user.id)
    if role != TeamRole.OWNER and user.role.value != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "仅队长可解散团队")
    await db.delete(t)
    await db.commit()
    return {"ok": True}


@router.post("/{team_id}/invite-codes")
async def create_invite_code(
    team_id: int, db: AsyncSession = Depends(get_db), user: User = CurrentUser,
):
    """生成邀请码（队长/副队）"""
    t = await db.get(Team, team_id)
    if t is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "团队不存在")
    await require_team_manage(db, team_id, user)
    code = secrets.token_urlsafe(8)
    _INVITE_CODES[code] = team_id
    return {"code": code}


@router.post("/join", status_code=201)
async def join_by_code(
    body: dict = Body(...),
    db: AsyncSession = Depends(get_db),
    user: User = CurrentUser,
):
    """凭邀请码加入团队（不知道 team_id 也可用；前端团队页加入入口）"""
    code = (body or {}).get("code", "")
    team_id = _INVITE_CODES.get(code)
    if team_id is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "邀请码无效")
    return await _do_join(db, team_id, user)


@router.post("/{team_id}/members", status_code=201)
async def join_team(
    team_id: int, body: dict = Body(...),
    db: AsyncSession = Depends(get_db), user: User = CurrentUser,
):
    """凭邀请码加入指定团队"""
    code = (body or {}).get("code", "")
    if _INVITE_CODES.get(code) != team_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "邀请码无效")
    return await _do_join(db, team_id, user)


async def _do_join(db: AsyncSession, team_id: int, user: User) -> dict:
    """加入团队公共逻辑：容量校验 + 去重 + 入队"""
    t = await db.get(Team, team_id)
    if t is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "团队不存在")
    count = await db.scalar(
        select(func.count())
        .select_from(TeamMember).where(TeamMember.team_id == team_id))
    if count >= t.max_members:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "团队人数已满")
    exists = await get_team_role(db, team_id, user.id)
    if exists:
        return {"ok": True, "already": True}
    db.add(TeamMember(team_id=team_id, user_id=user.id, role=TeamRole.MEMBER))
    await db.commit()
    return {"ok": True}


@router.delete("/{team_id}/members/{member_user_id}")
async def remove_member(
    team_id: int, member_user_id: int,
    db: AsyncSession = Depends(get_db), user: User = CurrentUser,
):
    """移除成员（队长/副队）；成员本人退出（member 角色）"""
    target_role = await get_team_role(db, team_id, member_user_id)
    if target_role is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "成员不存在")
    my_role = await get_team_role(db, team_id, user.id)
    is_self = member_user_id == user.id
    if not is_self and my_role not in (TeamRole.OWNER, TeamRole.ADMIN) and user.role.value != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "无权限移除成员")
    # 队长不可被移除（含队长本人退出——需先转让）
    if target_role == TeamRole.OWNER:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "队长需先转让后再退出")
    # 副队只能被队长移除
    if target_role == TeamRole.ADMIN and not is_self \
            and my_role != TeamRole.OWNER and user.role.value != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "副队长仅队长可移除")
    row = await db.scalar(
        select(TeamMember).where(
            TeamMember.team_id == team_id, TeamMember.user_id == member_user_id))
    await db.delete(row)
    await db.commit()
    return {"ok": True}


@router.put("/{team_id}/members/{member_user_id}/role")
async def set_member_role(
    team_id: int, member_user_id: int, body: dict = Body(...),
    db: AsyncSession = Depends(get_db), user: User = CurrentUser,
):
    """设置成员角色（副队/队员）；转让队长（仅队长）"""
    t = await db.get(Team, team_id)
    if t is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "团队不存在")
    new_role_str = (body or {}).get("role", "")
    try:
        new_role = TeamRole(new_role_str)
    except ValueError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "角色不合法")
    my_role = await get_team_role(db, team_id, user.id)
    target_role = await get_team_role(db, team_id, member_user_id)
    if target_role is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "成员不存在")

    if new_role == TeamRole.OWNER:
        # 转让队长：仅队长操作；原队长降为 admin
        if my_role != TeamRole.OWNER and user.role.value != "admin":
            raise HTTPException(status.HTTP_403_FORBIDDEN, "仅队长可转让队长")
        t.owner_id = member_user_id
        old_owner = await db.scalar(
            select(TeamMember).where(
                TeamMember.team_id == team_id, TeamMember.user_id == user.id))
        old_owner.role = TeamRole.ADMIN
        target = await db.scalar(
            select(TeamMember).where(
                TeamMember.team_id == team_id, TeamMember.user_id == member_user_id))
        target.role = TeamRole.OWNER
    else:
        # 设置 admin/member：队长或副队
        await require_team_manage(db, team_id, user)
        if target_role == TeamRole.OWNER:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "队长角色需通过转让设置")
        row = await db.scalar(
            select(TeamMember).where(
                TeamMember.team_id == team_id, TeamMember.user_id == member_user_id))
        row.role = new_role
    await db.commit()
    return {"ok": True}
