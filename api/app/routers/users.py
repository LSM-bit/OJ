"""用户路由：注册 / 登录 / 我的信息 / 个人资料编辑 / 头像上传"""

import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models import User, UserRole
from app.services.auth import CurrentUser
from app.services.security import create_access_token, hash_password, verify_password

router = APIRouter(prefix="/users", tags=["users"])

# 头像上传限制与存储目录（本地磁盘，生产可换对象存储）
AVATAR_MAX_BYTES = 2 * 1024 * 1024  # 2MB
AVATAR_ALLOWED_TYPES = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp",
                        "image/gif": ".gif"}


def _avatar_upload_dir() -> Path:
    """头像存储目录：{data_dir}/avatars（数据根目录下，随题目数据目录可配置）"""
    data_root = Path(settings.problem_data_dir).parent
    d = data_root / "avatars"
    d.mkdir(parents=True, exist_ok=True)
    return d


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
    avatar: str | None = None

    class Config:
        from_attributes = True


class ProfileUpdateRequest(BaseModel):
    """个人资料编辑：用户名/邮箱可改；密码修改需提供旧密码"""
    username: str | None = Field(default=None, min_length=2, max_length=32,
                                 pattern=r"^[a-zA-Z0-9_-]+$")
    email: str | None = Field(default=None, max_length=128)
    old_password: str | None = None
    new_password: str | None = Field(default=None, min_length=6, max_length=64)


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


@router.patch("/me", response_model=UserOut)
async def update_me(
    req: ProfileUpdateRequest,
    db: AsyncSession = Depends(get_db),
    user: User = CurrentUser,
):
    """编辑个人资料：用户名、邮箱、密码（改密码需校验旧密码）"""
    if req.username is not None and req.username != user.username:
        exists = await db.scalar(
            select(User).where(User.username == req.username, User.id != user.id))
        if exists:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "用户名已被占用")
        user.username = req.username
    if req.email is not None and req.email != user.email:
        exists = await db.scalar(select(User).where(User.email == req.email, User.id != user.id))
        if exists:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "邮箱已被占用")
        user.email = req.email
    if req.new_password is not None:
        if req.old_password is None or not verify_password(req.old_password, user.password_hash):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "旧密码错误")
        user.password_hash = hash_password(req.new_password)
    await db.commit()
    await db.refresh(user)
    return user


@router.post("/me/avatar", response_model=UserOut)
async def upload_avatar(
    file: UploadFile,
    db: AsyncSession = Depends(get_db),
    user: User = CurrentUser,
):
    """上传头像：≤2MB，仅常见图片格式；覆盖旧头像文件（不同用户互不影响）"""
    content_type = (file.content_type or "").lower()
    ext = AVATAR_ALLOWED_TYPES.get(content_type)
    if ext is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "仅支持 jpg/png/webp/gif 图片")
    data = await file.read()
    if len(data) > AVATAR_MAX_BYTES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "头像不能超过 2MB")
    if not data:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "文件为空")

    # 固定文件名 per 用户（覆盖写），避免历史文件堆积
    filename = f"u{user.id}{ext}"
    path = _avatar_upload_dir() / filename
    path.write_bytes(data)

    # 旧头像扩展名可能不同，清掉其它扩展名的同名文件
    for other_ext in AVATAR_ALLOWED_TYPES.values():
        if other_ext != ext:
            old = _avatar_upload_dir() / f"u{user.id}{other_ext}"
            old.unlink(missing_ok=True)

    user.avatar = f"/static/avatars/{filename}"
    await db.commit()
    await db.refresh(user)
    return user


@router.delete("/me/avatar", response_model=UserOut)
async def delete_avatar(
    db: AsyncSession = Depends(get_db),
    user: User = CurrentUser,
):
    """恢复默认头像：删除文件并清空字段"""
    for ext in AVATAR_ALLOWED_TYPES.values():
        (_avatar_upload_dir() / f"u{user.id}{ext}").unlink(missing_ok=True)
    user.avatar = None
    await db.commit()
    await db.refresh(user)
    return user
