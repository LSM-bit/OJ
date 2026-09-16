# -*- coding: utf-8 -*-
# ============================================================
# 文件: alembic/versions/dd44ee55ff66_assistant_conv_archived.py
# 用途: AI 助手迁移——assistant_conversations 加 archived 布尔列：
#       用户「删除」会话改为软删归档（行与消息留存后台），
#       存量行回填为未归档（False）。
# ============================================================
"""assistant conversations archive flag

用户删除 AI 聊天记录 = 归档而非物理删除：新增 archived 列，
NULL 不允许（存量回填 false），列表/续聊加载口按此过滤。
Revision ID: dd44ee55ff66
Revises: aa11bb22cc33
Create Date: 2026-09-16

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'dd44ee55ff66'
down_revision: Union[str, None] = 'aa11bb22cc33'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('assistant_conversations', sa.Column(
        'archived', sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade() -> None:
    op.drop_column('assistant_conversations', 'archived')
