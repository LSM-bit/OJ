"""合并 user_role 枚举：PROBLEM_SETTER/CONTEST_ADMIN -> USER（出题/建赛已放开给所有用户）

Revision ID: d1e2f3a4b5c6
Revises: 4c516d467454
Create Date: 2026-09-08
"""
from alembic import op

revision = "d1e2f3a4b5c6"
down_revision = "a7f3e2b91c04"
branch_labels = None
depends_on = None

OLD = "user_role_old"
NEW = "user_role"


def upgrade() -> None:
    # 1) 把两个废弃角色的存量用户降为 USER
    op.execute("UPDATE users SET role = 'USER' WHERE role IN ('PROBLEM_SETTER', 'CONTEST_ADMIN')")
    # 2) 重建枚举类型（PG 不支持直接删除枚举值）
    op.execute(f"ALTER TYPE {NEW} RENAME TO {OLD}")
    op.execute("CREATE TYPE user_role AS ENUM ('USER', 'ADMIN')")
    op.execute(f"ALTER TABLE users ALTER COLUMN role TYPE {NEW} USING role::text::{NEW}")
    op.execute(f"DROP TYPE {OLD}")


def downgrade() -> None:
    op.execute(f"ALTER TYPE {NEW} RENAME TO {OLD}")
    op.execute("CREATE TYPE user_role AS ENUM ('USER', 'PROBLEM_SETTER', 'CONTEST_ADMIN', 'ADMIN')")
    op.execute(f"ALTER TABLE users ALTER COLUMN role TYPE {NEW} USING role::text::{NEW}")
    op.execute(f"DROP TYPE {OLD}")
