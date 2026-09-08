"""路由权限依赖工厂：按路径参数加载资源并校验可见性/管理权

私有资源对无权者统一抛 404（与"不存在"同响应，防枚举探测）。

题目可见性特例（可见性只看载体，不看题目本身）：
  题目在题单/比赛内时，通过 ?playlist_id= / ?contest_id= 携带载体上下文，
  只要该载体对用户可见，题目即可见（无论题目 is_public 与否）。
"""

from typing import Any, Literal

from fastapi import Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Contest, ContestProblem, Playlist, PlaylistProblem, Problem
from app.services.access import can_manage, can_view
from app.services.auth import CurrentUser, get_optional_user


def _deny() -> HTTPException:
    return HTTPException(status.HTTP_404_NOT_FOUND, "资源不存在")


def _require(ok: bool) -> None:
    if not ok:
        raise _deny()


async def _problem_or_404(db: AsyncSession, problem_id: int) -> Problem:
    p = await db.get(Problem, problem_id)
    if p is None:
        raise _deny()
    return p


async def _contest_or_404(db: AsyncSession, contest_id: int) -> Contest:
    c = await db.get(Contest, contest_id)
    if c is None:
        raise _deny()
    return c


async def _playlist_or_404(db: AsyncSession, playlist_id: int) -> Playlist:
    pl = await db.get(Playlist, playlist_id)
    if pl is None:
        raise _deny()
    return pl


async def problem_view_allowed(
    db: AsyncSession, user, p: Problem,
    playlist_id: int | None = None, contest_id: int | None = None,
) -> bool:
    """题目读权限：题目自身可见性，或通过可见的题单/比赛间接授权"""
    if playlist_id is not None:
        pl = await db.get(Playlist, playlist_id)
        if pl is not None and await can_view(db, user, pl.owner_type, pl.owner_id, pl.is_public):
            in_pl = await db.scalar(
                select(PlaylistProblem.id).where(
                    PlaylistProblem.playlist_id == pl.id,
                    PlaylistProblem.problem_id == p.id))
            if in_pl is not None:
                return True
    if contest_id is not None:
        c = await db.get(Contest, contest_id)
        if c is not None and await can_view(db, user, c.owner_type, c.owner_id, c.is_public):
            in_ct = await db.scalar(
                select(ContestProblem.id).where(
                    ContestProblem.contest_id == c.id,
                    ContestProblem.problem_id == p.id))
            if in_ct is not None:
                return True
    return await can_view(db, user, p.owner_type, p.owner_id, p.is_public)


def ProblemAccess(action: Literal["view", "manage"] = "view"):
    """依赖工厂：加载题目并校验权限，返回 Problem ORM 对象

    view 时接受可选 query 参数 playlist_id / contest_id 作为间接授权上下文"""
    async def checker(
        problem_id: int,
        playlist_id: int | None = None,
        contest_id: int | None = None,
        db: AsyncSession = Depends(get_db),
        user=Depends(get_optional_user),
    ):
        p = await _problem_or_404(db, problem_id)
        if action == "manage":
            if user is None:
                raise HTTPException(status.HTTP_401_UNAUTHORIZED, "未登录")
            _require(await can_manage(db, user, p.owner_type, p.owner_id))
        else:
            _require(await problem_view_allowed(db, user, p, playlist_id, contest_id))
        return p
    return checker


def ContestAccess(action: Literal["view", "manage"] = "view"):
    """依赖工厂：加载比赛并校验权限，返回 Contest ORM 对象"""
    async def checker(
        contest_id: int,
        db: AsyncSession = Depends(get_db),
        user=Depends(get_optional_user),
    ):
        c = await _contest_or_404(db, contest_id)
        if action == "manage":
            if user is None:
                raise HTTPException(status.HTTP_401_UNAUTHORIZED, "未登录")
            _require(await can_manage(db, user, c.owner_type, c.owner_id))
        else:
            _require(await can_view(db, user, c.owner_type, c.owner_id, c.is_public))
        return c
    return checker


def PlaylistAccess(action: Literal["view", "manage"] = "view"):
    """依赖工厂：加载题单并校验权限，返回 Playlist ORM 对象"""
    async def checker(
        playlist_id: int,
        db: AsyncSession = Depends(get_db),
        user=Depends(get_optional_user),
    ):
        pl = await _playlist_or_404(db, playlist_id)
        if action == "manage":
            if user is None:
                raise HTTPException(status.HTTP_401_UNAUTHORIZED, "未登录")
            _require(await can_manage(db, user, pl.owner_type, pl.owner_id))
        else:
            _require(await can_view(db, user, pl.owner_type, pl.owner_id, pl.is_public))
        return pl
    return checker
