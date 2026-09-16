"""初始化默认管理员账号（幂等，可重复执行）

用法: .venv/Scripts/python -m app.scripts.create_admin
凭据经环境变量 ADMIN_USERNAME / ADMIN_PASSWORD 注入，
未设置时回退开发默认 Admin0 / Admin0（生产环境务必注入强密码）
"""

import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models import User, UserRole
from app.services.security import hash_password

DEFAULT_ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "Admin0")
DEFAULT_ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "Admin0")


async def create_admin(username: str = DEFAULT_ADMIN_USERNAME,
                       password: str = DEFAULT_ADMIN_PASSWORD) -> None:
    async with AsyncSessionLocal() as db:
        exists = await db.scalar(select(User).where(User.username == username))
        if exists:
            # 已存在则确保是管理员（幂等）
            if exists.role != UserRole.ADMIN:
                exists.role = UserRole.ADMIN
                await db.commit()
                print(f"用户 {username} 已存在，已提升为 ADMIN")
            else:
                print(f"管理员 {username} 已存在，跳过")
            return
        admin = User(
            username=username,
            email=f"{username.lower()}@oj.local",
            password_hash=hash_password(password),
            role=UserRole.ADMIN,
            rating=1500,
        )
        db.add(admin)
        await db.commit()
        print(f"默认管理员创建成功: {username} / ********（密码不回显）")


if __name__ == "__main__":
    asyncio.run(create_admin())
