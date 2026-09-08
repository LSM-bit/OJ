"""统一权限服务层：资源可见性 / 管理权 / 团队角色判定

可见性规则（题目/比赛/题单共用）：
  1. is_public = true
  2. owner_type=user 且 owner_id=当前用户
  3. owner_type=team 且当前用户是团队成员
  4. ADMIN 全量可见
私有资源对无权者一律按"不存在"处理（路由层抛 404，防枚举探测）。
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import OwnerType, Team, TeamMember, TeamRole, User, UserRole


async def get_team_role(db: AsyncSession, team_id: int, user_id: int) -> TeamRole | None:
    """用户在某团队中的角色；非成员返回 None"""
    return await db.scalar(
        select(TeamMember.role).where(
            TeamMember.team_id == team_id, TeamMember.user_id == user_id)
    )


async def is_team_member(db: AsyncSession, team_id: int, user_id: int) -> bool:
    return await get_team_role(db, team_id, user_id) is not None


async def can_view(
    db: AsyncSession, user: User | None,
    owner_type: OwnerType, owner_id: int, is_public: bool,
) -> bool:
    """资源可见性判定（读权限）。user 可为 None（未登录只看公有）"""
    if is_public:
        return True
    if user is None:
        return False
    if user.role == UserRole.ADMIN:
        return True
    if owner_type == OwnerType.USER:
        return owner_id == user.id
    # 团队资源：任何成员可见
    return await is_team_member(db, owner_id, user.id)


async def can_manage(
    db: AsyncSession, user: User,
    owner_type: OwnerType, owner_id: int,
) -> bool:
    """写权限：个人资源=本人；团队资源=队长/副队；ADMIN"""
    if user.role == UserRole.ADMIN:
        return True
    if owner_type == OwnerType.USER:
        return owner_id == user.id
    role = await get_team_role(db, owner_id, user.id)
    return role in (TeamRole.OWNER, TeamRole.ADMIN)


async def require_team_manage(db: AsyncSession, team_id: int, user: User) -> None:
    """校验用户对团队有管理权（队长/副队/ADMIN），否则 403"""
    from fastapi import HTTPException, status

    if user.role == UserRole.ADMIN:
        return
    role = await get_team_role(db, team_id, user.id)
    if role not in (TeamRole.OWNER, TeamRole.ADMIN):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "无团队管理权限")


async def team_of(db: AsyncSession, team_id: int) -> Team | None:
    return await db.get(Team, team_id)
