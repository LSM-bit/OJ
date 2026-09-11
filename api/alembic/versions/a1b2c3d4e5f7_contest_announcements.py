"""contest announcements table

比赛公告表：比赛创建者（或团队管理者）在比赛页内发布公告，参赛者可见
Revision ID: a1b2c3d4e5f7
Revises: f9a2b3c4d5e6
Create Date: 2026-09-11

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f7'
down_revision: Union[str, None] = 'f9a2b3c4d5e6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'contest_announcements',
        sa.Column('id', sa.BigInteger(), primary_key=True),
        sa.Column('contest_id', sa.BigInteger(),
                  sa.ForeignKey('contests.id', ondelete='CASCADE'), nullable=False),
        sa.Column('title', sa.String(128), nullable=False),
        sa.Column('content', sa.Text(), nullable=False, server_default=''),
        sa.Column('author_id', sa.BigInteger(),
                  sa.ForeignKey('users.id'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index('ix_contest_announcements_contest_id', 'contest_announcements',
                    ['contest_id'])


def downgrade() -> None:
    op.drop_index('ix_contest_announcements_contest_id', table_name='contest_announcements')
    op.drop_table('contest_announcements')
