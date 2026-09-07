"""题目路由：列表 / 详情 / 创建（出题人）/ 数据包上传"""

import json
import uuid

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    UploadFile,
    status,
)
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Problem, Submission, SubmissionStatus, Testcase, User, UserRole
from app.services.auth import Admin, CurrentUser, ProblemSetter
from app.services.problem_data import data_dir, write_problem_data

router = APIRouter(prefix="/problems", tags=["problems"])


class ProblemCreate(BaseModel):
    title: str = Field(min_length=1, max_length=128)
    description: str = Field(default="")
    difficulty: int = Field(default=1, ge=1, le=5)
    tags: list[str] = Field(default_factory=list)
    time_limit_ms: int = Field(default=2000, ge=100)
    memory_limit_mb: int = Field(default=256, ge=16)
    is_public: bool = False


class ProblemOut(BaseModel):
    id: int
    display_id: int
    title: str
    difficulty: int
    tags: list
    time_limit_ms: int = 2000
    memory_limit_mb: int = 256
    is_public: bool

    class Config:
        from_attributes = True


class ProblemDetailOut(ProblemOut):
    description: str
    owner_id: int


def _limits(problem: Problem) -> dict:
    return {
        "time_limit_ms": problem.config.get("time_limit_ms", 2000),
        "memory_limit_mb": problem.config.get("memory_limit_mb", 256),
    }


def _problem_out(p: Problem) -> ProblemOut:
    """从 ORM 对象构造 ProblemOut，从 config JSON 展开限制字段"""
    out = ProblemOut.model_validate(p)
    out.time_limit_ms = p.config.get("time_limit_ms", 2000)
    out.memory_limit_mb = p.config.get("memory_limit_mb", 256)
    return out


@router.get("", response_model=list[ProblemOut])
async def list_problems(
    page: int = 1, size: int = 50,
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Problem).where(Problem.is_public == True)  # noqa: E712
    total = await db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = await db.scalars(
        stmt.order_by(Problem.display_id).offset((page - 1) * size).limit(size)
    )
    items = []
    for p in rows:
        items.append(_problem_out(p))
    return items


@router.get("/{problem_id}", response_model=ProblemDetailOut)
async def get_problem(problem_id: int, db: AsyncSession = Depends(get_db)):
    p = await db.get(Problem, problem_id)
    if p is None or not p.is_public:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "题目不存在")
    out = ProblemDetailOut.model_validate(p)
    out.time_limit_ms = p.config.get("time_limit_ms", 2000)
    out.memory_limit_mb = p.config.get("memory_limit_mb", 256)
    return out


@router.post("", response_model=ProblemOut, status_code=201)
async def create_problem(
    req: ProblemCreate, db: AsyncSession = Depends(get_db), user: User = ProblemSetter
):
    display_id = await db.scalar(select(func.max(Problem.display_id))) or 0
    p = Problem(
        display_id=display_id + 1,
        title=req.title,
        description=req.description,
        difficulty=req.difficulty,
        tags=req.tags,
        config={
            "time_limit_ms": req.time_limit_ms,
            "memory_limit_mb": req.memory_limit_mb,
            "languages": ["python3.12", "cpp17", "c17", "java21"],
        },
        owner_id=user.id,
        is_public=req.is_public,
    )
    db.add(p)
    await db.commit()
    await db.refresh(p)
    out = ProblemOut.model_validate(p)
    out.time_limit_ms = req.time_limit_ms
    out.memory_limit_mb = req.memory_limit_mb
    return out


@router.post("/{problem_id}/data")
async def upload_problem_data(
    problem_id: int,
    file: UploadFile = File(...),
    data_version: str = Form("v1"),
    db: AsyncSession = Depends(get_db),
    user: User = ProblemSetter,
):
    """上传题目数据 zip 包：manifest.json + cases/*.in + cases/*.out"""
    p = await db.get(Problem, problem_id)
    if p is None or (p.owner_id != user.id and user.role != UserRole.ADMIN):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "题目不存在或无权限")
    content = await file.read()
    if len(content) > 64 * 1024 * 1024:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "数据包超过 64MB")
    files = _unzip_to_dict(content)
    try:
        await write_problem_data(str(p.id), data_version, files)
    except (KeyError, AssertionError) as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"数据包不合法: {e}") from e
    # 同步 testcases 表（判题时按 idx 取分值）
    manifest = json.loads(files["manifest.json"])
    for i, case in enumerate(manifest["cases"]):
        db.add(Testcase(problem_id=p.id, idx=i, case_id=case["id"],
                        input_key=f"cases/{case['id']}.in",
                        output_key=f"cases/{case['id']}.out",
                        score=case.get("score", 0)))
    # 更新题目 config 里的数据版本，触发节点缓存失效
    p.config = {**p.config, "data_version": data_version}
    await db.commit()
    return {"ok": True, "files": len(files), "cases": len(manifest["cases"])}


def _unzip_to_dict(content: bytes) -> dict[str, bytes]:
    import io
    import zipfile

    files: dict[str, bytes] = {}
    with zipfile.ZipFile(io.BytesIO(content)) as zf:
        for name in zf.namelist():
            if name.endswith("/"):
                continue
            files[name] = zf.read(name)
    return files
