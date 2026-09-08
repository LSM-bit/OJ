"""testcase is_sample column

Testcase 增加 is_sample 布尔列：
- True = 样例（题面对所有用户可见，随详情接口下发）
- False = 隐藏用例（仅出题人可见，用于判题）
存量数据全部视为隐藏用例（False，即列默认值）。
Revision ID: b8e2f1a34d56
Revises: d1e2f3a4b5c6
Create Date: 2026-09-08

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b8e2f1a34d56'
down_revision: Union[str, None] = 'd1e2f3a4b5c6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('testcases', sa.Column('is_sample', sa.Boolean(), nullable=False,
                                         server_default=sa.false()))


def downgrade() -> None:
    op.drop_column('testcases', 'is_sample')
