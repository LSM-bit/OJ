"""题目路由：列表 / 详情 / 创建（出题人）/ 数据包上传 / 用例管理 / 标程验证 / 发布

三步出题流程（前端向导）：
  1. 题面（基本信息 + Markdown 描述）
  2. 样例与用例（上传 zip：只需 *.in/*.out 成对用例文件，服务端自动配对生成分值；可单独补传样例）
  3. 测试（上传/指定标程，跑全部用例比对，全部通过后才能发布公开）
"""

import json
import uuid
from datetime import datetime, timezone

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    UploadFile,
    status,
)
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.judge_gateway.gen.judge.v1 import judge_pb2
from app.judge_gateway.server import get_gateway
from app.models import OwnerType, Problem, Submission, SubmissionStatus, Tag, Testcase, TeamMember, User, UserRole
from app.services.access_deps import ProblemAccess
from app.services.auth import CurrentUser, ProblemSetter, get_optional_user as get_optional_user_import
from app.services.problem_data import (
    append_files,
    pack_cases,
    read_manifest,
    read_text_file,
    write_manifest,
    write_problem_data,
)

router = APIRouter(prefix="/problems", tags=["problems"])


class ProblemCreate(BaseModel):
    title: str = Field(min_length=1, max_length=128)
    description: str = Field(default="")
    difficulty: int = Field(default=1, ge=1, le=5)
    tags: list[str] = Field(default_factory=list)
    time_limit_ms: int = Field(default=2000, ge=100)
    memory_limit_mb: int = Field(default=256, ge=16)
    owner_type: OwnerType = OwnerType.USER
    team_id: int | None = None  # owner_type=team 时必填
    # 注意：创建时不再接收 is_public —— 新题一律先存草稿，公开必须走第三步测试


class ProblemOut(BaseModel):
    id: int
    display_id: int
    title: str
    difficulty: int
    tags: list
    time_limit_ms: int = 2000
    memory_limit_mb: int = 256
    is_public: bool  # 出题视角需要区分草稿/已公开

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


@router.get("")
async def list_problems(
    page: int = 1, size: int = Query(default=50, ge=1, le=1000),
    mine: int = 0,  # 1 = 出题视角：我管理的（含未公开草稿）；0 = 刷题视角：公开题
    tag: str | None = None,  # 标签筛选：匹配 tags JSONB 数组任一元素（多个用逗号分隔，取交集）
    archived: int = 0,  # 1 = 仅看已归档题目（mine=1 出题视角下有效）；默认一律排除归档题
    full: int = 0,  # 1 = 返回 {total, items}（分页页需要总数）；默认返回裸数组（兼容旧调用方）
    did: int | None = None,  # 按题号精确查（题号跳转用，走当前视角的可见性规则）
    q: str | None = None,  # 标题模糊搜索（ilike）/ 纯数字时同时主题号
    db: AsyncSession = Depends(get_db),
    user: User | None = Depends(get_optional_user_import),
):
    """mine=0 刷题视角：公开题目；mine=1 出题视角：我拥有的 + 我团队的（含草稿，ADMIN 全量）
    tag=模拟,数学：题目 tags 数组需包含所有给定标签（JSONB 包含查询）
    归档题不进列表；mine=1 且 archived=1 时只看归档题（归档/恢复管理入口）
    page/size 分页（size 上限 1000）；did=N 按题号精确查；q=关键词标题模糊搜；
    full=1 时响应为 {"total": 总数, "items": [...]}，否则裸数组（兼容旧前端）"""
    is_archived = bool(archived)
    if mine:
        if user is None:
            return {"total": 0, "items": []} if full else []
        if user.role == UserRole.ADMIN:
            stmt = select(Problem)
        else:
            my_team_ids = select(TeamMember.team_id).where(TeamMember.user_id == user.id)
            stmt = select(Problem).where(
                ((Problem.owner_type == OwnerType.USER) & (Problem.owner_id == user.id))
                | ((Problem.owner_type == OwnerType.TEAM) & Problem.owner_id.in_(my_team_ids)))
        stmt = stmt.where(Problem.archived == is_archived)
    else:
        # 刷题视角：公开且未归档
        stmt = select(Problem).where(
            Problem.is_public == True,  # noqa: E712
            Problem.archived == False)  # noqa: E712
    # 标签筛选：tags 为 JSONB 数组，@> 按包含语义匹配（SQLite 测试环境降级为 LIKE）
    if tag:
        wanted = [t.strip() for t in tag.split(",") if t.strip()]
        if wanted:
            if db.bind.dialect.name == "sqlite":
                # SQLite：JSON 列按 json.dumps 默认 ensure_ascii=True 存转义文本
                # （"模拟" 存成 "模拟"），LIKE 模式需用同一转义形式；
                # SQLite LIKE 对 ASCII 大小写不敏感，a-f 十六进制无需额外归一
                for t in wanted:
                    stmt = stmt.where(Problem.tags.like(f'%{json.dumps(t)}%'))
            else:
                from sqlalchemy import text as sa_text
                # JSON 数组字面量（多标签 = 数组包含全部）；json.dumps 已把非 ASCII
                # 转义成 \uXXXX，再把单引号翻倍防 SQL 字面量逃逸
                arr = '[' + ','.join(json.dumps(t) for t in wanted) + ']'
                stmt = stmt.where(Problem.tags.op("@>")(sa_text(f"'{arr.replace(chr(39), chr(39)*2)}'::jsonb")))
    if did is not None:  # 题号精确查（跳转用）
        stmt = stmt.where(Problem.display_id == did)
    if q:  # 标题模糊搜索；纯数字关键词同时主题号（ilike 模式需转义 % _ 防注入通配）
        kw = f"%{q.strip().replace(chr(92), '').replace('%', '').replace('_', '')}%"
        cond = Problem.title.ilike(kw)
        if q.strip().isdigit():
            cond = cond | (Problem.display_id == int(q.strip()))
        stmt = stmt.where(cond)
    total = await db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = await db.scalars(
        stmt.order_by(Problem.display_id).offset((page - 1) * size).limit(size)
    )
    items = [_problem_out(p) for p in rows]
    if full:
        return {"total": total or 0, "items": items}
    return items


@router.get("/tags")
async def list_tags(db: AsyncSession = Depends(get_db)):
    """全站标签云：公开题目的标签及使用次数（降序），供前端筛选面板展示。归档题不计入"""
    rows = await db.scalars(select(Problem.tags).where(
        Problem.is_public == True,  # noqa: E712
        Problem.archived == False))  # noqa: E712
    counter: dict[str, int] = {}
    for tags in rows:
        # 同一题内重复标签只计一次（标签云语义：有多少道题用了它）
        for t in set(tags or []):
            if isinstance(t, str) and t:
                counter[t] = counter.get(t, 0) + 1
    items = [{"tag": t, "count": c} for t, c in sorted(counter.items(), key=lambda x: (-x[1], x[0]))]
    return {"items": items}


class TagCreate(BaseModel):
    name: str = Field(min_length=1, max_length=32)


@router.get("/tags/search")
async def search_tags(q: str = "", db: AsyncSession = Depends(get_db)):
    """标签实例搜索（出题弹窗 TagPicker 用）：从 tags 表按名称模糊匹配，空关键字返回全量（公开接口）"""
    stmt = select(Tag)
    if q.strip():
        stmt = stmt.where(Tag.name.ilike(f"%{q.strip()}%"))
    rows = await db.scalars(stmt.order_by(Tag.name).limit(100))
    return [{"id": t.id, "name": t.name} for t in rows]


@router.post("/tags", status_code=201)
async def create_tag(body: TagCreate, db: AsyncSession = Depends(get_db), user: User = CurrentUser):
    """创建标签实例（前台幂等：重名不报错，直接返回已有实例；管理端另走 /admin/tags 显式校验冲突）"""
    name = body.name.strip()
    if not name:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "标签名不能为空")
    dup = await db.scalar(select(Tag).where(Tag.name == name))
    if dup is not None:
        return {"id": dup.id, "name": dup.name}
    t = Tag(name=name)
    db.add(t)
    await db.commit()
    await db.refresh(t)
    return {"id": t.id, "name": t.name}


@router.get("/{problem_id}")
async def get_problem(
    p: Problem = Depends(ProblemAccess("view")),
    db: AsyncSession = Depends(get_db),
):
    out = ProblemDetailOut.model_validate(p)
    out.time_limit_ms = p.config.get("time_limit_ms", 2000)
    out.memory_limit_mb = p.config.get("memory_limit_mb", 256)
    # 样例随详情下发（题面可见部分）；隐藏用例绝不出现在此接口
    tcs = await db.scalars(
        select(Testcase).where(Testcase.problem_id == p.id, Testcase.is_sample == True)  # noqa: E712
        .order_by(Testcase.idx))
    version = p.config.get("data_version", "v1")
    samples = []
    for tc in tcs:
        inp = await read_text_file(str(p.id), version, tc.input_key, limit=4000) or ""
        out_text = await read_text_file(str(p.id), version, tc.output_key, limit=4000) or ""
        samples.append({"idx": tc.idx, "input": inp, "output": out_text})
    return {**out.model_dump(), "samples": samples}


@router.post("", response_model=ProblemOut, status_code=201)
async def create_problem(
    req: ProblemCreate, db: AsyncSession = Depends(get_db), user: User = ProblemSetter,
):
    # 归属个人或团队（团队需有管理权）
    if req.owner_type == OwnerType.TEAM:
        if not req.team_id:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "缺少 team_id")
        from app.services.access import require_team_manage
        from app.models import Team
        t = await db.get(Team, req.team_id)
        if t is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "团队不存在")
        await require_team_manage(db, req.team_id, user)
        owner_id = req.team_id
    else:
        owner_id = user.id
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
        owner_type=req.owner_type,
        owner_id=owner_id,
        is_public=False,  # 创建一律先为草稿，公开必须通过第三步测试后发布
    )
    db.add(p)
    await db.commit()
    await db.refresh(p)
    out = ProblemOut.model_validate(p)
    out.time_limit_ms = req.time_limit_ms
    out.memory_limit_mb = req.memory_limit_mb
    return out


class ProblemUpdate(BaseModel):
    """编辑题目：仅提供管理权校验后的可选字段
    注意：is_public 不在此处，可见性只能走 PUT /publish（硬校验验证凭证）"""
    title: str | None = Field(default=None, min_length=1, max_length=128)
    description: str | None = None
    difficulty: int | None = Field(default=None, ge=1, le=5)
    tags: list[str] | None = None
    time_limit_ms: int | None = Field(default=None, ge=100)
    memory_limit_mb: int | None = Field(default=None, ge=16)


@router.put("/{problem_id}", response_model=ProblemDetailOut)
async def update_problem(
    problem_id: int,
    req: ProblemUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = CurrentUser,
    p: Problem = Depends(ProblemAccess("manage")),
):
    """编辑题目（题面/限制/可见性）；权限 = 资源管理权（owner/团队队长副队/ADMIN）"""
    if req.title is not None:
        p.title = req.title
    if req.description is not None:
        p.description = req.description
    if req.difficulty is not None:
        p.difficulty = req.difficulty
    if req.tags is not None:
        p.tags = req.tags
    if req.time_limit_ms is not None or req.memory_limit_mb is not None:
        p.config = {
            **p.config,
            "time_limit_ms": req.time_limit_ms or p.config.get("time_limit_ms", 2000),
            "memory_limit_mb": req.memory_limit_mb or p.config.get("memory_limit_mb", 256),
        }
    # 注意：is_public 不允许通过普通编辑修改，只能走 /publish（校验验证凭证）
    await db.commit()
    await db.refresh(p)
    out = ProblemDetailOut.model_validate(p)
    out.time_limit_ms = p.config.get("time_limit_ms", 2000)
    out.memory_limit_mb = p.config.get("memory_limit_mb", 256)
    return out


@router.post("/{problem_id}/data")
async def upload_problem_data(
    problem_id: int,
    file: UploadFile = File(...),
    data_version: str = Form("v1"),
    db: AsyncSession = Depends(get_db),
    user: User = CurrentUser,
    p: Problem = Depends(ProblemAccess("manage")),
):
    """上传题目数据 zip 包：只需成对的用例文件 *.in + *.out（放 cases/ 子目录或根目录均可）。
    非用例文件（manifest.json 等杂物）自动丢弃；分值由服务端生成——
    stem 以 sample 开头视为样例（0 分），其余隐藏用例平分 100 分（余数给第一个）。
    zip 整体替换当前 data_version。
    权限：资源级管理权（owner/团队队长副队/ADMIN），不要求全局出题人角色"""
    content = await file.read()
    if len(content) > 64 * 1024 * 1024:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "数据包超过 64MB")
    try:
        files = pack_cases(_unzip_raw(content))
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e)) from e
    await write_problem_data(str(p.id), data_version, files)
    # 同步 testcases 表（判题时按 idx 取分值）；数据变了，验证凭证作废
    case_count = await _sync_testcases_from_manifest(db, p, files)
    p.config = {**p.config, "data_version": data_version,
                "verified_at": None, "solution_code": None, "solution_language": None}
    await db.commit()
    return {"ok": True, "files": len(files), "cases": case_count}


def _unzip_raw(content: bytes) -> dict[str, bytes]:
    """解 zip 为 {zip内路径: 内容}，目录项忽略；坏包转 400"""
    import io
    import zipfile

    files: dict[str, bytes] = {}
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as zf:
            for name in zf.namelist():
                if name.endswith("/"):
                    continue
                files[name] = zf.read(name)
    except zipfile.BadZipFile as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "不是合法的 zip 数据包") from e
    return files


# ---------- 三步出题：用例管理 / 标程验证 / 发布 ----------

async def _sync_testcases_from_manifest(db: AsyncSession, p: Problem, files: dict[str, bytes]) -> int:
    """按（服务端生成的）manifest 同步 testcases 表（数据包上传后调用），返回用例数
    manifest 条目带 "sample": true 标记样例；zip 整体替换时旧标记作废"""
    old = (await db.scalars(select(Testcase).where(Testcase.problem_id == p.id))).all()
    for r in old:
        await db.delete(r)
    # 先 flush 删除，避免 (problem_id, idx) 唯一约束在删除/插入同批执行时冲突
    await db.flush()
    manifest = json.loads(files["manifest.json"])
    for i, case in enumerate(manifest["cases"]):
        db.add(Testcase(problem_id=p.id, idx=i, case_id=case["id"],
                        input_key=f"cases/{case['id']}.in",
                        output_key=f"cases/{case['id']}.out",
                        score=case.get("score", 0),
                        is_sample=bool(case.get("sample", False))))
    return len(manifest["cases"])


@router.get("/{problem_id}/cases")
async def list_cases(
    p: Problem = Depends(ProblemAccess("manage")),
    db: AsyncSession = Depends(get_db),
):
    """用例列表（出题人视角）：样例与隐藏用例分开返回 + 标程/发布状态"""
    tcs = await db.scalars(
        select(Testcase).where(Testcase.problem_id == p.id).order_by(Testcase.idx))
    samples, hidden = [], []
    version = p.config.get("data_version", "v1")
    for tc in tcs:
        inp = await read_text_file(str(p.id), version, tc.input_key, limit=2000) or ""
        out = await read_text_file(str(p.id), version, tc.output_key, limit=2000) or ""
        item = {
            "idx": tc.idx, "case_id": tc.case_id, "score": tc.score,
            "is_sample": tc.is_sample,
            "input_preview": inp, "output_preview": out,
        }
        (samples if tc.is_sample else hidden).append(item)
    return {
        "samples": samples,
        "cases": hidden,
        "has_data": bool(samples or hidden),
        "data_version": p.config.get("data_version", "v1"),
        "solution_code": p.config.get("solution_code"),
        "solution_language": p.config.get("solution_language"),
        "verified_at": p.config.get("verified_at"),
        "is_public": p.is_public,
    }


@router.post("/{problem_id}/cases/sample")
async def add_sample_case(
    problem_id: int,
    body: dict,
    p: Problem = Depends(ProblemAccess("manage")),
    db: AsyncSession = Depends(get_db),
):
    """追加一个用例：body {"input": "...", "output": "...", "score": 10, "is_sample": true}
    is_sample=true → 样例（题面可见）；默认 False → 隐藏用例。
    直接落盘到当前数据版本目录并同步 testcases 表"""
    inp = body.get("input", "")
    out = body.get("output", "")
    is_sample = bool(body.get("is_sample", False))
    if not inp and not out:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "输入/输出不能同时为空")
    version = p.config.get("data_version", "v1")
    tcs = await db.scalars(
        select(Testcase).where(Testcase.problem_id == p.id).order_by(Testcase.idx))
    existing = list(tcs)
    idx = len(existing)
    case_id = f"tc{idx}"
    # manifest 同步追加
    manifest = {"cases": [{"id": tc.case_id, "score": tc.score, "sample": tc.is_sample}
                          for tc in existing]}
    manifest["cases"].append({"id": case_id, "score": body.get("score", 0), "sample": is_sample})
    # 新用例文件 + 重写后的 manifest 一并增量写入存储后端
    await append_files(str(p.id), version, {
        f"cases/{case_id}.in": inp.encode("utf-8"),
        f"cases/{case_id}.out": out.encode("utf-8"),
        "manifest.json": json.dumps(manifest, ensure_ascii=False).encode("utf-8"),
    })
    db.add(Testcase(problem_id=p.id, idx=idx, case_id=case_id,
                    input_key=f"cases/{case_id}.in", output_key=f"cases/{case_id}.out",
                    score=body.get("score", 0), is_sample=is_sample))
    await db.commit()
    return {"ok": True, "case_id": case_id, "idx": idx, "is_sample": is_sample}


@router.delete("/{problem_id}/cases/{idx}")
async def delete_case(
    idx: int,
    p: Problem = Depends(ProblemAccess("manage")),
    db: AsyncSession = Depends(get_db),
):
    """删除指定序号用例并重排（数据文件保留在目录中，manifest/testcases 同步）"""
    tcs = await db.scalars(
        select(Testcase).where(Testcase.problem_id == p.id).order_by(Testcase.idx))
    existing = list(tcs)
    if idx < 0 or idx >= len(existing):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "用例不存在")
    target = existing.pop(idx)
    await db.delete(target)
    await db.flush()  # 先落删除，避免重排 UPDATE 撞 (problem_id, idx) 唯一约束
    # 重排 idx 并同步 manifest
    version = p.config.get("data_version", "v1")
    manifest = {"cases": []}
    for i, tc in enumerate(existing):
        tc.idx = i
        manifest["cases"].append({"id": tc.case_id, "score": tc.score})
    if await read_manifest(str(p.id), version) is not None:
        await write_manifest(str(p.id), version, manifest)
    await db.commit()
    return {"ok": True, "count": len(existing)}


class SolutionReq(BaseModel):
    code: str = Field(min_length=1, max_length=100_000)
    language: str = Field(pattern="^(python3\\.12|cpp17|c17|java21)$")


RUN_STATUS_LABEL = {
    "finished": "运行完成", "runtime_error": "运行错误", "time_limit_exceeded": "超时",
    "memory_limit_exceeded": "超内存", "output_limit_exceeded": "输出超限",
    "compile_error": "编译错误", "system_error": "系统错误",
}


def _same_output(expected: str, actual: str) -> bool:
    """与判题节点一致：忽略行尾空格与末尾换行"""
    def norm(s: str) -> list[str]:
        return [ln.rstrip(" \t") for ln in s.splitlines() if ln.strip()]
    return norm(expected) == norm(actual)


@router.post("/{problem_id}/verify")
async def verify_solution(
    problem_id: int,
    req: SolutionReq,
    p: Problem = Depends(ProblemAccess("manage")),
    db: AsyncSession = Depends(get_db),
):
    """标程验证：用标程跑全部用例逐个比对（第三步「测试」）
    全部通过才允许 is_public=true 发布"""
    tcs = await db.scalars(
        select(Testcase).where(Testcase.problem_id == p.id).order_by(Testcase.idx))
    tcs = list(tcs)  # type: ignore[assignment]
    if not tcs:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "请先上传测试数据（第二步）")

    data_version = p.config.get("data_version", "v1")
    cases = [judge_pb2.TestCase(test_case_id=tc.case_id, score=tc.score) for tc in tcs]
    job = judge_pb2.SubmitJob(
        submission_id=f"verify-{uuid.uuid4().hex}",
        language=req.language,
        code=req.code.encode(),
        limits=judge_pb2.ResourceLimits(
            time_limit_ms=p.config.get("time_limit_ms", 2000),
            memory_limit_mb=p.config.get("memory_limit_mb", 256)),
        problem_id=str(p.id),
        data_version=data_version,
        cases=cases,
        stop_on_failure=False,  # 验证跑完全部用例，给出完整报告
    )
    try:
        result = await get_gateway().submit(job, timeout=180)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, f"判题节点不可用: {e}") from e

    detail = []
    all_pass = True
    for i, c in enumerate(result.cases):
        passed = c.status == "accepted"
        all_pass = all_pass and passed
        exp_out = ""
        if i < len(tcs):
            exp_out = await read_text_file(
                str(p.id), data_version, tcs[i].output_key, limit=2000) or ""
        detail.append({
            "idx": i, "case_id": tcs[i].case_id if i < len(tcs) else c.test_case_id,
            "status": c.status, "passed": passed,
            "time_used_ms": c.time_used_ms, "memory_used_kb": c.memory_used_kb,
            "expected_preview": exp_out,
        })
    # 全部通过：保存标程与验证时间（发布凭证）
    if all_pass and result.status == "accepted":
        p.config = {**p.config, "solution_code": req.code,
                    "solution_language": req.language,
                    "verified_at": datetime.now(timezone.utc).isoformat()}
        await db.commit()
    return {
        "ok": all_pass, "total": len(detail),
        "passed": sum(1 for d in detail if d["passed"]),
        "cases": detail,
        "error_message": result.error_message,
        "verified": all_pass,
    }


@router.put("/{problem_id}/publish")
async def publish_problem(
    problem_id: int,
    body: dict,
    p: Problem = Depends(ProblemAccess("manage")),
    db: AsyncSession = Depends(get_db),
):
    """发布/存草稿/撤回。
    is_public=true：硬校验（有测试数据 + 已通过标程验证）后才公开
    is_public=false：保存为草稿（不公开，无需验证凭证）"""
    want_public = bool(body.get("is_public", True))
    if want_public:
        tc_count = await db.scalar(
            select(func.count()).select_from(Testcase).where(Testcase.problem_id == p.id))
        if not tc_count:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "发布失败：请先上传测试数据")
        if not p.config.get("verified_at"):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "发布失败：请先通过标程验证（第三步测试）")
    p.is_public = want_public
    await db.commit()
    return {"ok": True, "is_public": p.is_public}


@router.put("/{problem_id}/archive")
async def archive_problem(
    problem_id: int,
    body: dict,
    p: Problem = Depends(ProblemAccess("manage")),
    db: AsyncSession = Depends(get_db),
):
    """归档/取消归档。body {"archived": true|false}
    归档后：不进题目列表（公开/管理视角均默认排除），不可再提交；
    详情页仍可访问（已有引用不失效），可随时恢复。"""
    want_archived = bool(body.get("archived", True))
    p.archived = want_archived
    await db.commit()
    return {"ok": True, "archived": p.archived}
