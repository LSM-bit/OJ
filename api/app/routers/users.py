"""用户路由：注册 / 登录 / 我的信息"""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import User, UserRole
from app.services.auth import CurrentUser
from app.services.security import create_access_token, hash_password, verify_password

router = APIRouter(prefix="/users", tags=["users"])


class RegisterRequest(BaseModel):
    username: str = Field(min_length=2, max_length=32, pattern=r"^[a-zA-Z0-9_-]+$")
    email: str = Field(max_length=128)
    password: str = Field(min_length=6, max_length=64)


class LoginRequest(BaseModel):
    username: str
    password: str


class UserOut(BaseModel):
    id: int
    username: str
    email: str
    role: str
    rating: int

    class Config:
        from_attributes = True


@router.post("/register", response_model=UserOut, status_code=201)
async def register(req: RegisterRequest, db: AsyncSession = Depends(get_db)):
    exists = await db.scalar(
        select(User).where((User.username == req.username) | (User.email == req.email))
    )
    if exists:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "用户名或邮箱已存在")
    user = User(
        username=req.username,
        email=req.email,
        password_hash=hash_password(req.password),
        role=UserRole.USER,
    )
    db.add(user)
    await db.commit()
    return user


@router.post("/login")
async def login(req: LoginRequest, db: AsyncSession = Depends(get_db)):
    user = await db.scalar(select(User).where(User.username == req.username))
    if user is None or not verify_password(req.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "用户名或密码错误")
    if user.banned:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "账号已封禁")
    token = create_access_token(user.id, user.role.value)
    return {"access_token": token, "token_type": "bearer",
            "user": UserOut.model_validate(user)}


@router.get("/me", response_model=UserOut)
async def me(user: User = CurrentUser):
    return user
