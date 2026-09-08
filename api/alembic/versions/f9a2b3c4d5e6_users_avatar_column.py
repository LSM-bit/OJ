"""users avatar column

用户头像字段：存上传后的 URL 相对路径（/static/avatars/xxx.png），NULL = 无头像（前端用首字母兜底）
Revision ID: f9a2b3c4d5e6
Revises: 4c516d467454
Create Date: 2026-09-08

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f9a2b3c4d5e6'
down_revision: Union[str, None] = 'c3d4e5f6a7b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('users', sa.Column('avatar', sa.String(256), nullable=True))


def downgrade() -> None:
    op.drop_column('users', 'avatar')
