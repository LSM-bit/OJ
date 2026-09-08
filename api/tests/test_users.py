"""测试用户与认证：注册 / 登录 / me / 权限边界"""

import pytest
from httpx import AsyncClient

from app.models import UserRole

pytestmark = pytest.mark.asyncio


async def _register(client: AsyncClient, username: str, **kw) -> dict:
    body = {"username": username, "email": kw.get("email", f"{username}@t.co"),
            "password": kw.get("password", "pass123456")}
    return await client.post("/users/register", json=body)


async def test_register_and_login_flow(client: AsyncClient):
    r = await _register(client, "bob")
    assert r.status_code == 201, r.text
    assert r.json()["username"] == "bob"
    assert r.json()["role"] == "user"

    r = await client.post("/users/login",
                          json={"username": "bob", "password": "pass123456"})
    assert r.status_code == 200, r.text
    token = r.json()["access_token"]
    assert token

    r = await client.get("/users/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert r.json()["username"] == "bob"


async def test_register_duplicate_username(client: AsyncClient):
    await _register(client, "dup")
    r = await _register(client, "dup", email="other@t.co")
    assert r.status_code == 400
    r = await _register(client, "dup2", email="dup@t.co")
    assert r.status_code == 400  # 邮箱撞第一个用户的


async def test_register_invalid_username(client: AsyncClient):
    r = await _register(client, "x")          # 太短
    assert r.status_code == 422
    r = await _register(client, "bad name!")  # 非法字符
    assert r.status_code == 422


async def test_login_wrong_password(client: AsyncClient):
    await _register(client, "carl")
    r = await client.post("/users/login",
                          json={"username": "carl", "password": "wrong-pass"})
    assert r.status_code == 401


async def test_me_requires_auth(client: AsyncClient):
    r = await client.get("/users/me")
    assert r.status_code == 401


async def test_me_invalid_token(client: AsyncClient):
    r = await client.get("/users/me", headers={"Authorization": "Bearer garbage"})
    assert r.status_code == 401


async def test_banned_user_cannot_login_or_pass_auth(client, db_sessionmaker):
    from tests.conftest import make_user

    async with db_sessionmaker() as db:
        u = await make_user(db, "banned", UserRole.USER)
        u.banned = True
        await db.commit()
        uid = u.id

    r = await client.post("/users/login",
                          json={"username": "banned", "password": "pass123456"})
    assert r.status_code == 403

    # 直接拿有效 token 也会被拦
    from app.services.security import create_access_token
    token = create_access_token(uid, "user")
    r = await client.get("/users/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 401
