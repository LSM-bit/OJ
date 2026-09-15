"""SQLAlchemy 模型（阶段 0 骨架：核心表结构）

主键统一用应用层雪花 ID（app.utils.snowflake），不用数据库自增：
- 分布式友好、ID 含时间信息、避免自增 ID 泄露业务量
- BigInteger 列存储，default=snowflake_pk 在 Python 端生成
"""

from datetime import datetime
from enum import Enum as PyEnum

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.utils.snowflake import next_id


def snowflake_pk() -> int:
    """雪花主键默认值（insert 时逐行调用）"""
    return next_id()


class UserRole(str, PyEnum):
    USER = "user"
    ADMIN = "admin"


class OwnerType(str, PyEnum):
    USER = "user"
    TEAM = "team"


class TeamRole(str, PyEnum):
    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"


class SubmissionStatus(str, PyEnum):
    WAITING = "waiting"
    JUDGING = "judging"
    COMPILE_ERROR = "ce"
    WRONG_ANSWER = "wa"
    TIME_LIMIT_EXCEEDED = "tle"
    MEMORY_LIMIT_EXCEEDED = "mle"
    RUNTIME_ERROR = "re"
    OUTPUT_LIMIT_EXCEEDED = "ole"
    ACCEPTED = "ac"
    SYSTEM_ERROR = "se"


class ContestRule(str, PyEnum):
    ACM = "acm"
    OI = "oi"
    IOI = "ioi"


class ContestStatus(str, PyEnum):
    UPCOMING = "upcoming"
    RUNNING = "running"
    ENDED = "ended"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, default=snowflake_pk)
    username: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    email: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(128))
    role: Mapped[UserRole] = mapped_column(Enum(UserRole, name="user_role"), default=UserRole.USER)
    rating: Mapped[int] = mapped_column(Integer, default=1500)
    avatar: Mapped[str | None] = mapped_column(String(256))  # 头像 URL 相对路径，NULL = 用首字母兜底
    banned: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    submissions: Mapped[list["Submission"]] = relationship(back_populates="user")


class Problem(Base):
    __tablename__ = "problems"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, default=snowflake_pk)
    display_id: Mapped[int] = mapped_column(Integer, unique=True, index=True)  # 对外展示题号
    title: Mapped[str] = mapped_column(String(128))
    description: Mapped[str] = mapped_column(Text)  # Markdown + LaTeX
    difficulty: Mapped[int] = mapped_column(Integer, default=1)  # 1-5
    tags: Mapped[list] = mapped_column(JSONB, default=list)
    # 判题配置：time_limit_ms / memory_limit_mb / languages / spj 等
    config: Mapped[dict] = mapped_column(JSONB, default=dict)
    owner_type: Mapped[OwnerType] = mapped_column(
        Enum(OwnerType, name="owner_type"), default=OwnerType.USER)
    owner_id: Mapped[int] = mapped_column(BigInteger)  # 多态：user.id 或 team.id（由 owner_type 消歧）
    is_public: Mapped[bool] = mapped_column(Boolean, default=False)
    # 归档：不出现在题目列表（公开/管理视角均默认排除），详情仍可访问，不可再提交
    archived: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    testcases: Mapped[list["Testcase"]] = relationship(back_populates="problem")


class Testcase(Base):
    __tablename__ = "testcases"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, default=snowflake_pk)
    problem_id: Mapped[int] = mapped_column(ForeignKey("problems.id", ondelete="CASCADE"), index=True)
    idx: Mapped[int] = mapped_column(Integer)  # 测试点序号，从 0 开始
    case_id: Mapped[str] = mapped_column(String(64))  # 数据包内的测试点 ID（文件名）
    input_key: Mapped[str] = mapped_column(String(256))   # 相对题目数据目录的路径
    output_key: Mapped[str] = mapped_column(String(256))
    score: Mapped[int] = mapped_column(Integer, default=10)   # OI 赛制分值
    is_sample: Mapped[bool] = mapped_column(Boolean, default=False)  # 样例=题面可见；False=隐藏用例
    time_limit_ms: Mapped[int | None] = mapped_column(Integer)  # None = 用题目默认
    memory_limit_mb: Mapped[int | None] = mapped_column(Integer)

    problem: Mapped["Problem"] = relationship(back_populates="testcases")

    __table_args__ = (Index("uq_testcase_problem_idx", "problem_id", "idx", unique=True),)


class Tag(Base):
    """标签实例表：题目标签统一从本表选择（name 唯一），problems.tags 仍存名称字符串数组
    建表与存量导入见 alembic 迁移 e6f7a8b9c0d1_tag_table.py
    """
    __tablename__ = "tags"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, default=snowflake_pk)
    name: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Submission(Base):
    __tablename__ = "submissions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, default=snowflake_pk)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    problem_id: Mapped[int] = mapped_column(ForeignKey("problems.id"), index=True)
    contest_id: Mapped[int | None] = mapped_column(ForeignKey("contests.id"), index=True)
    language: Mapped[str] = mapped_column(String(32))
    code_key: Mapped[str] = mapped_column(String(256))  # 对象存储 key
    code: Mapped[str | None] = mapped_column(Text)  # 源码留存（支持后台重判；旧提交为 NULL）
    status: Mapped[SubmissionStatus] = mapped_column(
        Enum(SubmissionStatus, name="submission_status"), default=SubmissionStatus.WAITING
    )
    score: Mapped[int] = mapped_column(Integer, default=0)
    time_ms: Mapped[int] = mapped_column(Integer, default=0)
    memory_kb: Mapped[int] = mapped_column(Integer, default=0)
    # 判题详情 JSON：[{idx, status, time_ms, memory_kb, message}]
    detail: Mapped[dict | None] = mapped_column(JSONB)
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    judged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user: Mapped["User"] = relationship(back_populates="submissions")
    problem: Mapped["Problem"] = relationship()


class Contest(Base):
    __tablename__ = "contests"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, default=snowflake_pk)
    title: Mapped[str] = mapped_column(String(128))
    description: Mapped[str] = mapped_column(Text, default="")
    rule: Mapped[ContestRule] = mapped_column(Enum(ContestRule, name="contest_rule"))
    status: Mapped[ContestStatus] = mapped_column(
        Enum(ContestStatus, name="contest_status"), default=ContestStatus.UPCOMING
    )
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    board_freeze_minutes: Mapped[int] = mapped_column(Integer, default=0)  # 封榜分钟数，0 = 不封榜
    is_public: Mapped[bool] = mapped_column(Boolean, default=True)  # 公有/私有比赛
    owner_type: Mapped[OwnerType] = mapped_column(
        Enum(OwnerType, name="owner_type"), default=OwnerType.USER)
    owner_id: Mapped[int] = mapped_column(BigInteger)  # 多态：user.id 或 team.id
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ContestParticipant(Base):
    __tablename__ = "contest_participants"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, default=snowflake_pk)
    contest_id: Mapped[int] = mapped_column(ForeignKey("contests.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    rank: Mapped[int] = mapped_column(Integer, default=0)
    penalty: Mapped[int] = mapped_column(Integer, default=0)  # 罚时（分钟）
    score: Mapped[int] = mapped_column(Integer, default=0)

    user: Mapped["User"] = relationship()

    __table_args__ = (Index("uq_participant", "contest_id", "user_id", unique=True),)


class ContestProblem(Base):
    __tablename__ = "contest_problems"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, default=snowflake_pk)
    contest_id: Mapped[int] = mapped_column(ForeignKey("contests.id", ondelete="CASCADE"), index=True)
    problem_id: Mapped[int] = mapped_column(ForeignKey("problems.id"))
    alias: Mapped[str] = mapped_column(String(8))  # 比赛内题号 A/B/C...


class Discussion(Base):
    __tablename__ = "discussions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, default=snowflake_pk)
    author_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    node: Mapped[str] = mapped_column(String(32), index=True)  # 版块：help/share/talk
    title: Mapped[str] = mapped_column(String(128))
    content: Mapped[str] = mapped_column(Text)
    top: Mapped[bool] = mapped_column(Boolean, default=False)
    replies_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, default=snowflake_pk)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    type: Mapped[str] = mapped_column(String(32))
    payload: Mapped[dict] = mapped_column(JSONB, default=dict)
    read: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Team(Base):
    """团队：发起人=队长（owner），成员经邀请码加入"""
    __tablename__ = "teams"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, default=snowflake_pk)
    name: Mapped[str] = mapped_column(String(64), unique=True)
    description: Mapped[str] = mapped_column(Text, default="")
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    max_members: Mapped[int] = mapped_column(Integer, default=50)
    # 归档：团队转为只读（不出现在团队列表、成员不可加入，名下题目/题单/比赛照常存在）
    archived: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    members: Mapped[list["TeamMember"]] = relationship(
        back_populates="team", cascade="all, delete-orphan")


class TeamMember(Base):
    __tablename__ = "team_members"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, default=snowflake_pk)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    role: Mapped[TeamRole] = mapped_column(Enum(TeamRole, name="team_member_role"),
                                           default=TeamRole.MEMBER)
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    team: Mapped["Team"] = relationship(back_populates="members")
    user: Mapped["User"] = relationship()

    __table_args__ = (Index("uq_team_member", "team_id", "user_id", unique=True),)


class Playlist(Base):
    """题单：公有/私有，归属个人或团队"""
    __tablename__ = "playlists"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, default=snowflake_pk)
    title: Mapped[str] = mapped_column(String(128))
    description: Mapped[str] = mapped_column(Text, default="")
    is_public: Mapped[bool] = mapped_column(Boolean, default=False)
    owner_type: Mapped[OwnerType] = mapped_column(
        Enum(OwnerType, name="owner_type"), default=OwnerType.USER)
    owner_id: Mapped[int] = mapped_column(BigInteger)  # 多态：user.id 或 team.id
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PlaylistProblem(Base):
    __tablename__ = "playlist_problems"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, default=snowflake_pk)
    playlist_id: Mapped[int] = mapped_column(
        ForeignKey("playlists.id", ondelete="CASCADE"), index=True)
    problem_id: Mapped[int] = mapped_column(ForeignKey("problems.id"))
    idx: Mapped[int] = mapped_column(Integer, default=0)  # 题单内顺序

    problem: Mapped["Problem"] = relationship()

    __table_args__ = (Index("uq_playlist_problem", "playlist_id", "problem_id", unique=True),)


class Announcement(Base):
    """公告：管理员发布，展示在主页公告栏（置顶优先，新的在前）"""
    __tablename__ = "announcements"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, default=snowflake_pk)
    title: Mapped[str] = mapped_column(String(128))
    content: Mapped[str] = mapped_column(Text, default="")
    top: Mapped[bool] = mapped_column(Boolean, default=False)  # 置顶
    author_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ContestAnnouncement(Base):
    """比赛公告：比赛管理者（创建者/团队管理）发布，仅比赛页面内可见"""
    __tablename__ = "contest_announcements"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, default=snowflake_pk)
    contest_id: Mapped[int] = mapped_column(
        ForeignKey("contests.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(128))
    content: Mapped[str] = mapped_column(Text, default="")
    author_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CheckIn(Base):
    """每日打卡：一人一天一条（uq 唯一约束兜底），连续天数应用层计算"""
    __tablename__ = "checkins"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, default=snowflake_pk)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    day: Mapped[str] = mapped_column(String(10))  # UTC 日期 YYYY-MM-DD
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (Index("uq_checkin_user_day", "user_id", "day", unique=True),)


class AssistantConversation(Base):
    """AI 助手会话（docs/AI助手Agent设计.md §3）：context 携带题目/提交上下文"""
    __tablename__ = "assistant_conversations"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, default=snowflake_pk)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    title: Mapped[str] = mapped_column(String(128), default="新对话")  # 一期取首条消息截断
    # {"type":"problem","problem_id":123} / {"type":"submission","submission_id":45} / {}
    context: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class AssistantMessage(Base):
    """AI 助手消息：content 为 Anthropic content blocks 原样（含 tool_use/tool_result），供回放与续聊。
    role='user' 的行同时用于日配额计数（按 created_at 日期 count）"""
    __tablename__ = "assistant_messages"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, default=snowflake_pk)
    conversation_id: Mapped[int] = mapped_column(
        ForeignKey("assistant_conversations.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(16))  # user / assistant
    content: Mapped[list] = mapped_column(JSONB, default=list)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AssistantToolCall(Base):
    """助手工具调用流水：一期只为 run_on_sample 的日配额计数（按日 count），
    兼作审计线索（谁在何时用了哪个工具）"""
    __tablename__ = "assistant_tool_calls"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, default=snowflake_pk)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    tool: Mapped[str] = mapped_column(String(32))
    conversation_id: Mapped[int | None] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
