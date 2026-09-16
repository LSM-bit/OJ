"""公告与打卡路由

公告：管理员发布/管理，所有人可见（主页公告栏）
打卡：登录用户每日一次，返回连续打卡天数与累计天数
"""
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Announcement, CheckIn, User, UserRole
from app.services.auth import CurrentUser, get_optional_user, require_admin

router = APIRouter(prefix="/misc", tags=["misc"])


# ---------------- 公告 ----------------

class AnnouncementCreate(BaseModel):
    title: str = Field(min_length=1, max_length=128)
    content: str = ""
    top: bool = False


class AnnouncementUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=128)
    content: Optional[str] = None
    top: Optional[bool] = None


def _ann_out(a: Announcement) -> dict:
    return {
        "id": a.id, "title": a.title, "content": a.content, "top": a.top,
        "created_at": a.created_at.isoformat(),
    }


@router.get("/announcements")
async def list_announcements(
    limit: int = 10,
    db: AsyncSession = Depends(get_db),
    _user: User | None = Depends(get_optional_user),
):
    """公告列表：置顶优先，新的在前（未登录也可看）"""
    rows = await db.scalars(
        select(Announcement)
        .order_by(Announcement.top.desc(), Announcement.created_at.desc())
        .limit(min(limit, 50)))
    return [_ann_out(a) for a in rows]


@router.post("/announcements", status_code=201)
async def create_announcement(
    req: AnnouncementCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_admin),
):
    a = Announcement(title=req.title, content=req.content, top=req.top, author_id=user.id)
    db.add(a)
    await db.commit()
    await db.refresh(a)
    return _ann_out(a)


@router.put("/announcements/{announcement_id}")
async def update_announcement(
    announcement_id: int,
    req: AnnouncementUpdate,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_admin),
):
    """编辑公告：标题/正文/置顶，按需局部更新（只覆盖显式传入的字段）"""
    a = await db.get(Announcement, announcement_id)
    if a is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "公告不存在")
    if req.title is not None:
        a.title = req.title
    if req.content is not None:
        a.content = req.content
    if req.top is not None:
        a.top = req.top
    await db.commit()
    await db.refresh(a)
    return _ann_out(a)


@router.delete("/announcements/{announcement_id}")
async def delete_announcement(
    announcement_id: int,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_admin),
):
    a = await db.get(Announcement, announcement_id)
    if a is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "公告不存在")
    await db.delete(a)
    await db.commit()
    return {"ok": True}


# ---------------- 打卡 ----------------

def _today_str() -> str:
    """UTC 日期串（打卡以自然日为单位）"""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


@router.get("/checkin")
async def checkin_status(
    db: AsyncSession = Depends(get_db),
    user: User = CurrentUser,
):
    """打卡状态：今日是否已打卡 + 连续天数 + 累计天数 + 最近打卡日"""
    today = _today_str()
    checked_today = await db.scalar(
        select(func.count()).select_from(CheckIn)
        .where(CheckIn.user_id == user.id, CheckIn.day == today)) > 0
    # 最近 400 天的打卡日，计算连续天数（从今天/昨天往回数）
    since = (datetime.now(timezone.utc) - timedelta(days=400)).strftime("%Y-%m-%d")
    rows = (await db.scalars(
        select(CheckIn.day).where(CheckIn.user_id == user.id, CheckIn.day >= since))).all()
    days = set(rows)
    streak = 0
    cursor = datetime.now(timezone.utc)
    if today not in days:
        cursor -= timedelta(days=1)  # 今天还没打，从昨天起算连续
    while cursor.strftime("%Y-%m-%d") in days:
        streak += 1
        cursor -= timedelta(days=1)
    total = await db.scalar(
        select(func.count()).select_from(CheckIn).where(CheckIn.user_id == user.id))
    return {
        "checked_today": checked_today,
        "streak": streak,
        "total": total or 0,
        "today": today,
    }


@router.post("/checkin", status_code=201)
async def checkin(
    db: AsyncSession = Depends(get_db),
    user: User = CurrentUser,
):
    """今日打卡：一人一天一条，重复打卡返回已有状态"""
    today = _today_str()
    exists = await db.scalar(
        select(func.count()).select_from(CheckIn)
        .where(CheckIn.user_id == user.id, CheckIn.day == today))
    if exists:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "今天已经打过卡啦")
    db.add(CheckIn(user_id=user.id, day=today))
    await db.commit()
    return {"ok": True, "day": today}
