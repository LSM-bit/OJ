# -*- coding: utf-8 -*-
# ============================================================
# 文件: alembic/versions/aa11bb22cc33_assistant_tables.py
# 用途: AI 助手迁移——新建 assistant_conversations / assistant_messages 两张表
#       （设计见 docs/AI助手Agent设计.md §3；消息 content 存 Anthropic blocks 原样）
# ============================================================
"""assistant conversation & message tables

AI 助手 Agent（独立节点化）落库：会话（含题目/提交上下文 JSON）与消息
（content blocks + token 用量；user 行兼作日配额计数）。
Revision ID: aa11bb22cc33
Revises: f7b3c9d2e8a1
Create Date: 2026-09-15

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'aa11bb22cc33'
down_revision: Union[str, None] = 'f7b3c9d2e8a1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'assistant_conversations',
        sa.Column('id', sa.BigInteger(), primary_key=True),
        sa.Column('user_id', sa.BigInteger(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('title', sa.String(128), nullable=False, server_default='新对话'),
        sa.Column('context', postgresql.JSONB(), nullable=False, server_default='{}'),
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
    )
    op.create_index('ix_assistant_conv_user', 'assistant_conversations', ['user_id'])
    op.create_table(
        'assistant_messages',
        sa.Column('id', sa.BigInteger(), primary_key=True),
        sa.Column('conversation_id', sa.BigInteger(),
                  sa.ForeignKey('assistant_conversations.id', ondelete='CASCADE'),
                  nullable=False),
        sa.Column('role', sa.String(16), nullable=False),
        sa.Column('content', postgresql.JSONB(), nullable=False, server_default='[]'),
        sa.Column('input_tokens', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('output_tokens', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
    )
    op.create_index('ix_assistant_msg_conv', 'assistant_messages', ['conversation_id'])
    op.create_table(
        'assistant_tool_calls',
        sa.Column('id', sa.BigInteger(), primary_key=True),
        sa.Column('user_id', sa.BigInteger(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('tool', sa.String(32), nullable=False),
        sa.Column('conversation_id', sa.BigInteger(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
    )
    op.create_index('ix_assistant_tool_user', 'assistant_tool_calls', ['user_id'])


def downgrade() -> None:
    op.drop_table('assistant_tool_calls')
    op.drop_table('assistant_messages')
    op.drop_table('assistant_conversations')
