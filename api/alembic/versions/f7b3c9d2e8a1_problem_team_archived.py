# -*- coding: utf-8 -*-
# ============================================================
# 文件: alembic/versions/f7b3c9d2e8a1_problem_team_archived.py
# 用途: 归档功能迁移——problems / teams 两表各加 archived 布尔字段
#       默认 false，存量行无需回填（server_default 兜底）
# ============================================================
"""problem & team archived flags

归档功能：problems.archived（题目归档，列表默认隐藏、禁止提交）、
teams.archived（团队归档，转为只读）。
Revision ID: f7b3c9d2e8a1
Revises: e6f7a8b9c0d1
Create Date: 2026-09-11

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f7b3c9d2e8a1'
down_revision: Union[str, None] = 'e6f7a8b9c0d1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'problems',
        sa.Column('archived', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column(
        'teams',
        sa.Column('archived', sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade() -> None:
    op.drop_column('teams', 'archived')
    op.drop_column('problems', 'archived')
