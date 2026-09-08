"""snowflake primary keys

所有表主键改为应用层雪花 ID：
- 去掉 nextval 序列默认值（模型已用 default=snowflake_pk 在 Python 端生成）
- 旧自增 ID 偏移 +10^15，避免与雪花 ID（时间戳在高位，数值远大于 10^15）空间冲突
Revision ID: a7f3e2b91c04
Revises: 4c516d467454
Create Date: 2026-09-08

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'a7f3e2b91c04'
down_revision: Union[str, None] = '4c516d467454'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# 需要改主键的全部表
TABLES = [
    'users', 'problems', 'testcases', 'submissions', 'contests',
    'contest_participants', 'contest_problems', 'discussions', 'notifications',
    'teams', 'team_members', 'playlists', 'playlist_problems',
]

# (表, 引用列)：全部外键/多态 owner 引用，需与主键同步偏移
REF_COLS = [
    ('testcases', 'problem_id'),
    ('submissions', 'user_id'),
    ('submissions', 'problem_id'),
    ('submissions', 'contest_id'),
    ('contest_participants', 'contest_id'),
    ('contest_participants', 'user_id'),
    ('contest_problems', 'contest_id'),
    ('contest_problems', 'problem_id'),
    ('discussions', 'author_id'),
    ('notifications', 'user_id'),
    ('teams', 'owner_id'),
    ('team_members', 'team_id'),
    ('team_members', 'user_id'),
    ('playlist_problems', 'playlist_id'),
    ('playlist_problems', 'problem_id'),
    ('problems', 'owner_id'),   # 多态：user.id 或 team.id
    ('contests', 'owner_id'),   # 多态
    ('playlists', 'owner_id'),  # 多态
]

# FK 完整定义：upgrade 里 drop → 偏移 → 重建
FKS = [
    # (表, 约束名, 引用列, 目标表, 级联)
    ('testcases', 'testcases_problem_id_fkey', 'problem_id', 'problems', 'CASCADE'),
    ('submissions', 'submissions_user_id_fkey', 'user_id', 'users', None),
    ('submissions', 'submissions_problem_id_fkey', 'problem_id', 'problems', None),
    ('submissions', 'submissions_contest_id_fkey', 'contest_id', 'contests', None),
    ('contest_participants', 'contest_participants_contest_id_fkey', 'contest_id', 'contests', 'CASCADE'),
    ('contest_participants', 'contest_participants_user_id_fkey', 'user_id', 'users', None),
    ('contest_problems', 'contest_problems_contest_id_fkey', 'contest_id', 'contests', 'CASCADE'),
    ('contest_problems', 'contest_problems_problem_id_fkey', 'problem_id', 'problems', None),
    ('discussions', 'discussions_author_id_fkey', 'author_id', 'users', None),
    ('notifications', 'notifications_user_id_fkey', 'user_id', 'users', None),
    ('teams', 'teams_owner_id_fkey', 'owner_id', 'users', None),
    ('team_members', 'team_members_team_id_fkey', 'team_id', 'teams', 'CASCADE'),
    ('team_members', 'team_members_user_id_fkey', 'user_id', 'users', None),
    ('playlist_problems', 'playlist_problems_playlist_id_fkey', 'playlist_id', 'playlists', 'CASCADE'),
    ('playlist_problems', 'playlist_problems_problem_id_fkey', 'problem_id', 'problems', None),
]

OFFSET = 10 ** 15  # 旧 ID 偏移量：与雪花 ID（~10^18 级）隔离


def upgrade() -> None:
    # 外键约束会拦截「引用列先偏移、主键还没偏移」的中间态（Postgres 逐语句检查 FK），
    # 因此先临时删掉全部 FK，偏移完再重建
    for table, name, _col, _ref, _on in FKS:
        op.execute(f'ALTER TABLE {table} DROP CONSTRAINT IF EXISTS {name}')

    for table, col in REF_COLS:
        op.execute(
            f'UPDATE {table} SET {col} = {col} + {OFFSET} '
            f'WHERE {col} IS NOT NULL AND {col} < {OFFSET}')
    for t in TABLES:
        # 去掉 nextval 默认值；新 ID 由应用层雪花生成
        op.execute(f'ALTER TABLE {t} ALTER COLUMN id DROP DEFAULT')
        op.execute(f'UPDATE {t} SET id = id + {OFFSET} WHERE id < {OFFSET}')

    # 重建 FK（引用列与目标主键都已偏移，重新可校验）
    for table, name, col, ref, on_delete in FKS:
        rule = f' ON DELETE {on_delete}' if on_delete else ''
        op.execute(f'ALTER TABLE {table} ADD CONSTRAINT {name} '
                   f'FOREIGN KEY ({col}) REFERENCES {ref}(id){rule}')


def downgrade() -> None:
    # 不可逆：仅回退偏移，恢复序列默认值需按各表旧序列起始值手工处理
    for t in TABLES:
        op.execute(f'UPDATE {t} SET id = id - {OFFSET} WHERE id >= {OFFSET} AND id < {OFFSET * 2}')
    for table, col in REF_COLS:
        op.execute(
            f'UPDATE {table} SET {col} = {col} - {OFFSET} '
            f'WHERE {col} IS NOT NULL AND {col} >= {OFFSET} AND {col} < {OFFSET * 2}')
