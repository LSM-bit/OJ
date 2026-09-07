"""SQLAlchemy 模型（阶段 0 骨架：核心表结构）"""

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


class UserRole(str, PyEnum):
    USER = "user"
    PROBLEM_SETTER = "problem_setter"
    CONTEST_ADMIN = "contest_admin"
    ADMIN = "admin"


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

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    email: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(128))
    role: Mapped[UserRole] = mapped_column(Enum(UserRole, name="user_role"), default=UserRole.USER)
    rating: Mapped[int] = mapped_column(Integer, default=1500)
    banned: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    submissions: Mapped[list["Submission"]] = relationship(back_populates="user")


class Problem(Base):
    __tablename__ = "problems"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    display_id: Mapped[int] = mapped_column(Integer, unique=True, index=True)  # 对外展示题号
    title: Mapped[str] = mapped_column(String(128))
    description: Mapped[str] = mapped_column(Text)  # Markdown + LaTeX
    difficulty: Mapped[int] = mapped_column(Integer, default=1)  # 1-5
    tags: Mapped[list] = mapped_column(JSONB, default=list)
    # 判题配置：time_limit_ms / memory_limit_mb / languages / spj 等
    config: Mapped[dict] = mapped_column(JSONB, default=dict)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    is_public: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    testcases: Mapped[list["Testcase"]] = relationship(back_populates="problem")


class Testcase(Base):
    __tablename__ = "testcases"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    problem_id: Mapped[int] = mapped_column(ForeignKey("problems.id", ondelete="CASCADE"), index=True)
    idx: Mapped[int] = mapped_column(Integer)  # 测试点序号，从 0 开始
    case_id: Mapped[str] = mapped_column(String(64))  # 数据包内的测试点 ID（文件名）
    input_key: Mapped[str] = mapped_column(String(256))   # 相对题目数据目录的路径
    output_key: Mapped[str] = mapped_column(String(256))
    score: Mapped[int] = mapped_column(Integer, default=10)   # OI 赛制分值
    time_limit_ms: Mapped[int | None] = mapped_column(Integer)  # None = 用题目默认
    memory_limit_mb: Mapped[int | None] = mapped_column(Integer)

    problem: Mapped["Problem"] = relationship(back_populates="testcases")

    __table_args__ = (Index("uq_testcase_problem_idx", "problem_id", "idx", unique=True),)


class Submission(Base):
    __tablename__ = "submissions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    problem_id: Mapped[int] = mapped_column(ForeignKey("problems.id"), index=True)
    contest_id: Mapped[int | None] = mapped_column(ForeignKey("contests.id"), index=True)
    language: Mapped[str] = mapped_column(String(32))
    code_key: Mapped[str] = mapped_column(String(256))  # 对象存储 key
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

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(128))
    description: Mapped[str] = mapped_column(Text, default="")
    rule: Mapped[ContestRule] = mapped_column(Enum(ContestRule, name="contest_rule"))
    status: Mapped[ContestStatus] = mapped_column(
        Enum(ContestStatus, name="contest_status"), default=ContestStatus.UPCOMING
    )
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    board_freeze_minutes: Mapped[int] = mapped_column(Integer, default=0)  # 封榜分钟数，0 = 不封榜
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ContestParticipant(Base):
    __tablename__ = "contest_participants"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    contest_id: Mapped[int] = mapped_column(ForeignKey("contests.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    rank: Mapped[int] = mapped_column(Integer, default=0)
    penalty: Mapped[int] = mapped_column(Integer, default=0)  # 罚时（分钟）
    score: Mapped[int] = mapped_column(Integer, default=0)

    __table_args__ = (Index("uq_participant", "contest_id", "user_id", unique=True),)


class ContestProblem(Base):
    __tablename__ = "contest_problems"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    contest_id: Mapped[int] = mapped_column(ForeignKey("contests.id", ondelete="CASCADE"), index=True)
    problem_id: Mapped[int] = mapped_column(ForeignKey("problems.id"))
    alias: Mapped[str] = mapped_column(String(8))  # 比赛内题号 A/B/C...


class Discussion(Base):
    __tablename__ = "discussions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    author_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    node: Mapped[str] = mapped_column(String(32), index=True)  # 版块：help/share/talk
    title: Mapped[str] = mapped_column(String(128))
    content: Mapped[str] = mapped_column(Text)
    top: Mapped[bool] = mapped_column(Boolean, default=False)
    replies_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    type: Mapped[str] = mapped_column(String(32))
    payload: Mapped[dict] = mapped_column(JSONB, default=dict)
    read: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
