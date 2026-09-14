# -*- coding: utf-8 -*-
# ============================================================
# 文件: alembic/versions/e6f7a8b9c0d1_tag_table.py
# 用途: 标签表迁移——建 tags 表（标签实例，name 唯一）
#       迁移前 problems.tags JSONB 内的存量标签自动导入 tags 表
# ============================================================
"""tags table

标签实例表：题目标签不再是自由文本，创建/使用时统一从 tags 表选择。
存量数据迁移：把 problems.tags JSONB 数组里已有的标签灌入 tags 表。
Revision ID: e6f7a8b9c0d1
Revises: a1b2c3d4e5f7
Create Date: 2026-09-11

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e6f7a8b9c0d1'
down_revision: Union[str, None] = 'a1b2c3d4e5f7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    tags = op.create_table(
        'tags',
        sa.Column('id', sa.BigInteger(), primary_key=True),
        sa.Column('name', sa.String(32), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index('uq_tags_name', 'tags', ['name'], unique=True)

    # 存量导入：把 problems.tags JSONB 中已有标签去重灌入（主键由应用层雪花生成，
    # 此处用随机 19 位整数占位——迁移期单线程执行，无冲突风险）
    conn = op.get_bind()
    if conn.dialect.name == 'postgresql':
        import random
        used: set[int] = set()

        def _sid() -> int:
            # int64 上限 2^63-1 ≈ 9.22e18，取 [2^62, 2^63) 避免越界
            while True:
                v = random.randint(2 ** 62, 2 ** 63 - 1)
                if v not in used:
                    used.add(v)
                    return v

        rows = conn.execute(sa.text(
            "SELECT DISTINCT jsonb_array_elements_text(tags) AS name "
            "FROM problems WHERE jsonb_typeof(tags) = 'array' AND jsonb_array_length(tags) > 0"
        )).fetchall()
        names = sorted({r.name for r in rows if r.name and r.name.strip()})
        for name in names:
            conn.execute(
                sa.text("INSERT INTO tags (id, name) VALUES (:id, :name)"),
                {"id": _sid(), "name": name},
            )


def downgrade() -> None:
    op.drop_index('uq_tags_name', table_name='tags')
    op.drop_table('tags')
