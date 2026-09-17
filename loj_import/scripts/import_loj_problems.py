# =============================================================
# 文件: loj_import/scripts/import_loj_problems.py
# 用途: 把 fetch_loj_problems.py 爬取的产物（loj_import/data/{题号}/
#       problem.json + data.zip）导入本 OJ 题库：
#       1. 创建 Problem（display_id 自增，题面/难度/限制取自 problem.json）
#       2. 用 pack_cases 从 zip 中只取成对 .in/.out 重新生成规范数据包
#          （manifest 由服务端规则生成；样例名以 sample 开头或旧 manifest
#           sample=true 标记的视为样例）；problem.json 里的样例并入后一起写
#       3. 复用路由的 _sync_testcases_from_manifest 同步 testcases 表
#       已导入过（同标题）的题自动跳过，可重复执行。
# 用法: cd api && .venv/Scripts/python.exe ../loj_import/scripts/import_loj_problems.py [--only 1,100,102]
# =============================================================

import argparse
import asyncio
import json
import sys
import zipfile
from pathlib import Path

# 容器内 app 包在 /app/app/，本地开发在 ../api/app/
# 自动探测：优先 /app（容器），回退 ../api（本地）
_app_root = Path(__file__).resolve().parents[2]
if not (_app_root / "app" / "__init__.py").exists():
    _app_root = _app_root / "api"
sys.path.insert(0, str(_app_root))

from sqlalchemy import func, select

from app.database import AsyncSessionLocal
from app.models import Problem, User, UserRole
from app.routers.problems import _sync_testcases_from_manifest
from app.services.problem_data import pack_cases, write_problem_data

IMPORT_ROOT = Path(__file__).resolve().parents[1] / "data"


def load_dir(d: Path) -> tuple[dict, dict[str, bytes]]:
    """读一个题目目录，返回 (problem.json 内容, zip 文件字典)"""
    pj = json.loads((d / "problem.json").read_text(encoding="utf-8"))
    with zipfile.ZipFile(d / "data.zip") as zf:
        files = {n: zf.read(n) for n in zf.namelist() if not n.endswith("/")}
    return pj, files


def sample_ids_of(files: dict[str, bytes]) -> set[str]:
    """旧包 manifest 里 sample=true 的用例名（清洗后的规范包同样适用）"""
    raw = files.get("manifest.json")
    if not raw:
        return set()
    try:
        return {c["id"] for c in json.loads(raw)["cases"] if c.get("sample")}
    except (ValueError, KeyError, TypeError):
        return set()


async def import_one(db, pj: dict, files: dict[str, bytes], admin: User) -> tuple[Problem, int, int]:
    """导入单题：建 Problem → 样例并入数据包 → pack_cases 规范打包 → 写存储 → 同步 testcases 表
    返回 (题目, 隐藏用例数, 样例数)"""
    display_id = (await db.scalar(select(func.max(Problem.display_id))) or 0) + 1
    p = Problem(
        display_id=display_id,
        title=pj["title"],
        description=pj["description"],
        difficulty=pj.get("difficulty", 1),
        tags=pj.get("tags", []),
        config={
            "time_limit_ms": pj.get("time_limit_ms", 2000),
            "memory_limit_mb": pj.get("memory_limit_mb", 256),
            "languages": ["python3.12", "cpp17", "c17", "java21"],
            "source": pj.get("source", ""),  # 题源备注（如 LibreOJ #100）
            "data_version": "v1",
        },
        owner_id=admin.id,
        is_public=True,
    )
    db.add(p)
    await db.commit()
    await db.refresh(p)

    # 题面样例并入用例集合：stem 命名 sample{i}，与隐藏用例 tc{i} 区分；
    # pack_cases 统一丢弃杂物、自然排序、按规则生成分值与 manifest
    sample_ids = sample_ids_of(files)
    for i, s in enumerate(pj.get("samples", [])):
        stem = f"sample{i}"
        inp = (s.get("inputData") or s.get("input") or "") + "\n"
        out = (s.get("outputData") or s.get("output") or "") + "\n"
        files[f"cases/{stem}.in"] = inp.encode("utf-8")
        files[f"cases/{stem}.out"] = out.encode("utf-8")
        sample_ids.add(stem)

    packed = pack_cases(files, sample_ids)
    await write_problem_data(str(p.id), "v1", packed)
    await _sync_testcases_from_manifest(db, p, packed)
    await db.commit()
    manifest = json.loads(packed["manifest.json"])
    n_sample = sum(1 for c in manifest["cases"] if c.get("sample"))
    return p, len(manifest["cases"]) - n_sample, n_sample


async def main() -> None:
    parser = argparse.ArgumentParser(description="导入 LOJ 爬取产物到题库")
    parser.add_argument("--only", type=str, default="",
                        help="仅导入指定目录名（逗号分隔，如 1,100,102），默认全部")
    args = parser.parse_args()
    wanted = {s.strip() for s in args.only.split(",") if s.strip()}

    if not IMPORT_ROOT.is_dir():
        print(f"目录不存在: {IMPORT_ROOT}（请先运行 fetch_loj_problems.py 爬取）")
        return

    async with AsyncSessionLocal() as db:
        admin = await db.scalar(select(User).where(User.role == UserRole.ADMIN))
        if not admin:
            print("错误: 未找到管理员用户，请先运行 create_admin 脚本")
            return

        ok = skipped = failed = 0
        for d in sorted(IMPORT_ROOT.iterdir()):
            if not d.is_dir() or not (d / "problem.json").is_file():
                continue
            if wanted and d.name not in wanted:
                continue
            try:
                pj, files = load_dir(d)
                exists = await db.scalar(select(Problem).where(Problem.title == pj["title"]))
                if exists:
                    print(f"- {d.name} 《{pj['title']}》 已存在（#{exists.display_id}），跳过")
                    skipped += 1
                    continue
                p, n_hidden, n_sample = await import_one(db, pj, files, admin)
                print(f"+ 导入 #{p.display_id} 《{p.title}》 "
                      f"（{n_hidden} 测试点 + {n_sample} 样例，"
                      f"DB id={p.id}，数据已写入存储后端）")
                ok += 1
            except Exception as exc:  # noqa: BLE001
                # 单题失败不中断整体导入，回滚当前事务继续下一题
                print(f"! 失败 {d.name}: {exc}")
                await db.rollback()
                failed += 1
        print(f"完成：成功 {ok}，跳过 {skipped}，失败 {failed}")


if __name__ == "__main__":
    asyncio.run(main())
