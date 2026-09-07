"""提交路由：创建提交（触发判题）+ 查询提交/结果"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.judge_gateway.gen.judge.v1 import judge_pb2
from app.judge_gateway.server import get_gateway
from app.models import Problem, Submission, SubmissionStatus, Testcase, User, UserRole
from app.services.auth import CurrentUser

router = APIRouter(prefix="/submissions", tags=["submissions"])

# 状态中文映射（前端展示）
STATUS_LABEL = {
    "waiting": "等待判题", "judging": "判题中", "ce": "编译错误", "wa": "答案错误",
    "tle": "超时", "mle": "超内存", "re": "运行错误", "ole": "输出超限",
    "ac": "通过", "se": "系统错误",
}
# 节点状态字符串 → DB 枚举
NODE_STATUS_MAP = {
    "accepted": SubmissionStatus.ACCEPTED,
    "wrong_answer": SubmissionStatus.WRONG_ANSWER,
    "time_limit_exceeded": SubmissionStatus.TIME_LIMIT_EXCEEDED,
    "memory_limit_exceeded": SubmissionStatus.MEMORY_LIMIT_EXCEEDED,
    "output_limit_exceeded": SubmissionStatus.OUTPUT_LIMIT_EXCEEDED,
    "runtime_error": SubmissionStatus.RUNTIME_ERROR,
    "compile_error": SubmissionStatus.COMPILE_ERROR,
    "system_error": SubmissionStatus.SYSTEM_ERROR,
}


class SubmissionCreate(BaseModel):
    problem_id: int
    language: str = Field(pattern="^(python3\\.12|cpp17|c17|java21)$")
    code: str = Field(min_length=1, max_length=100_000)


class CaseResultOut(BaseModel):
    idx: int
    status: str
    time_used_ms: int
    memory_used_kb: int
    score: int


class SubmissionOut(BaseModel):
    id: int
    problem_id: int
    language: str
    status: str
    status_label: str
    score: int
    time_ms: int
    memory_kb: int
    submitted_at: str

    class Config:
        from_attributes = True


@router.post("", response_model=SubmissionOut, status_code=201)
async def create_submission(
    req: SubmissionCreate,
    db: AsyncSession = Depends(get_db),
    user: User = CurrentUser,
):
    p = await db.get(Problem, req.problem_id)
    if p is None or not p.is_public:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "题目不存在")

    sub = Submission(
        user_id=user.id,
        problem_id=p.id,
        language=req.language,
        code_key=f"submissions/{uuid.uuid4().hex}",  # 二期改对象存储；DB 暂存 code 由 judge 传文本
        status=SubmissionStatus.WAITING,
    )
    db.add(sub)
    await db.flush()

    testcases = await db.scalars(
        select(Testcase).where(Testcase.problem_id == p.id).order_by(Testcase.idx)
    )
    tcs = list(testcases)
    if not tcs:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "题目暂无测试数据")
    await db.commit()

    data_version = p.config.get("data_version", "v1")
    job = judge_pb2.SubmitJob(
        submission_id=str(sub.id),
        language=req.language,
        code=req.code.encode(),
        limits=judge_pb2.ResourceLimits(
            time_limit_ms=p.config.get("time_limit_ms", 2000),
            memory_limit_mb=p.config.get("memory_limit_mb", 256),
        ),
        problem_id=str(p.id),
        data_version=data_version,
        cases=[judge_pb2.TestCase(test_case_id=tc.case_id, score=tc.score)
               for tc in tcs],
        stop_on_failure=True,  # ACM 默认；OI 赛制在比赛路由里另发
    )

    # 判题（异步等结果；高峰期由网关排队）
    gw = get_gateway()
    result = await gw.submit(job, timeout=120)

    sub.status = NODE_STATUS_MAP.get(result.status, SubmissionStatus.SYSTEM_ERROR)
    sub.score = result.score
    sub.time_ms = result.time_used_ms
    sub.memory_kb = result.memory_used_kb
    sub.detail = {
        "cases": [{"idx": i, "status": c.status,
                   "time_used_ms": c.time_used_ms, "memory_used_kb": c.memory_used_kb}
                  for i, c in enumerate(result.cases)],
        "error_message": result.error_message,
    }
    await db.commit()
    return _to_out(sub)


def _to_out(sub: Submission) -> SubmissionOut:
    return SubmissionOut(
        id=sub.id, problem_id=sub.problem_id, language=sub.language,
        status=sub.status.value, status_label=STATUS_LABEL[sub.status.value],
        score=sub.score, time_ms=sub.time_ms, memory_kb=sub.memory_kb,
        submitted_at=sub.submitted_at.isoformat(),
    )


@router.get("", response_model=list[SubmissionOut])
async def my_submissions(
    problem_id: int | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = CurrentUser,
):
    stmt = select(Submission).where(Submission.user_id == user.id)
    if problem_id:
        stmt = stmt.where(Submission.problem_id == problem_id)
    rows = await db.scalars(stmt.order_by(Submission.id.desc()).limit(50))
    return [_to_out(s) for s in rows]


@router.get("/{submission_id}")
async def submission_detail(
    submission_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = CurrentUser,
):
    sub = await db.get(Submission, submission_id)
    if sub is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "提交不存在")
    is_owner = sub.user_id == user.id
    is_admin = user.role == UserRole.ADMIN
    if not (is_owner or is_admin):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "无权查看该提交")
    out = _to_out(sub)
    detail = sub.detail or {}
    # 非管理员隐藏具体输出细节（防攻击/防抄题）
    return {**out.model_dump(), "detail": detail.get("cases", []),
            "error_message": detail.get("error_message", "") if is_owner or is_admin else ""}
