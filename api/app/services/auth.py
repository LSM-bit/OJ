"""认证依赖：当前用户 / 权限校验

角色只剩 USER / ADMIN：出题、建赛等创作权限放开给所有登录用户，
资源级权限（owner/团队管理权）见 services/access.py；/admin/* 整组走 require_admin。
"""

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt as jose_jwt
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models import User, UserRole

bearer = HTTPBearer(auto_error=False)


async def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: AsyncSession = Depends(get_db),
) -> User:
    if creds is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "未登录")
    try:
        payload = jose_jwt.decode(
            creds.credentials, settings.jwt_secret, algorithms=[settings.jwt_algorithm]
        )
    except JWTError as e:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "登录已过期") from e
    user = await db.get(User, int(payload["sub"]))
    if user is None or user.banned:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "账号不可用")
    return user


# 常用依赖
CurrentUser = Depends(get_current_user)


async def require_admin(user: User = Depends(get_current_user)) -> User:
    """后台整组强校验：仅 ADMIN（/admin/* 路由组挂 Depends(require_admin)）"""
    if user.role != UserRole.ADMIN:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "需要管理员权限")
    return user


# 出题/建赛已放开给所有登录用户（原 PROBLEM_SETTER/CONTEST_ADMIN 角色废弃）；
# 保留两个兼容依赖别名，均为「仅要求登录」
ProblemSetterDep = CurrentUser
ContestAdminDep = CurrentUser
ProblemSetter = ProblemSetterDep


async def get_optional_user(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: AsyncSession = Depends(get_db),
):
    """未登录返回 None（浏览题目/榜单用）；User | None 注解会干扰 FastAPI 响应模型推断，故不标注"""
    if creds is None:
        return None
    try:
        return await get_current_user(creds, db)
    except HTTPException:
        return None
