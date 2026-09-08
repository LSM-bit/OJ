"""add announcements and checkins

公告表（管理员发布，主页公告栏）+ 打卡表（一人一天一条，唯一约束兜底）
Revision ID: c3d4e5f6a7b8
Revises: b8e2f1a34d56
Create Date: 2026-09-08
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c3d4e5f6a7b8'
down_revision: Union[str, None] = 'b8e2f1a34d56'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'announcements',
        sa.Column('id', sa.BigInteger(), primary_key=True),
        sa.Column('title', sa.String(128), nullable=False),
        sa.Column('content', sa.Text(), nullable=False, server_default=''),
        sa.Column('top', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('author_id', sa.BigInteger(),
                  sa.ForeignKey('users.id', name='fk_announcement_author'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index('ix_announcements_author_id', 'announcements', ['author_id'])

    op.create_table(
        'checkins',
        sa.Column('id', sa.BigInteger(), primary_key=True),
        sa.Column('user_id', sa.BigInteger(),
                  sa.ForeignKey('users.id', name='fk_checkin_user'), nullable=False),
        sa.Column('day', sa.String(10), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index('ix_checkins_user_id', 'checkins', ['user_id'])
    op.create_unique_constraint('uq_checkin_user_day', 'checkins', ['user_id', 'day'])


def downgrade() -> None:
    op.drop_constraint('uq_checkin_user_day', 'checkins', type_='unique')
    op.drop_index('ix_checkins_user_id', table_name='checkins')
    op.drop_table('checkins')
    op.drop_index('ix_announcements_author_id', table_name='announcements')
    op.drop_table('announcements')
