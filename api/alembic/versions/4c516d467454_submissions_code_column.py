"""submissions code column

Revision ID: 4c516d467454
Revises: 451bbb44d861
Create Date: 2026-09-07 23:34:39.783984

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlalchemy.dialects.postgresql as pg


# revision identifiers, used by Alembic.
revision: str = '4c516d467454'
down_revision: Union[str, None] = '451bbb44d861'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 源码留存（TEXT），支持后台重判；历史提交为 NULL → 重判接口拒绝
    op.add_column('submissions', sa.Column('code', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('submissions', 'code')
