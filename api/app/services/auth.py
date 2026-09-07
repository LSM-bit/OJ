"""认证依赖：当前用户 / 权限校验（RBAC）"""

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt as jose_jwt
from sqlalchemy import select
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


def require_role(*roles: UserRole):
    """路由依赖：require_role(UserRole.ADMIN) 等"""
    allowed = {r.value for r in roles}

    async def checker(user: User = Depends(get_current_user)) -> User:
        if user.role.value not in allowed and user.role != UserRole.ADMIN:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "权限不足")
        return user

    return checker


# 常用依赖
CurrentUser = Depends(get_current_user)
ProblemSetter = Depends(require_role(UserRole.PROBLEM_SETTER, UserRole.CONTEST_ADMIN, UserRole.ADMIN))
Admin = Depends(require_role(UserRole.ADMIN))


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
