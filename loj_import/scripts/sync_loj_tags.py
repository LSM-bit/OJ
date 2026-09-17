# =============================================================
# 文件: loj_import/scripts/sync_loj_tags.py
# 用途: 为 LOJ 爬取产物补齐算法标签并同步到题库：
#       1. 扫描 loj_import/data/{题号}/problem.json，按目录名（LOJ displayId）
#          从 queryProblemSet 列表接口批量拉取标签（getProblem 详情不返回 tags），
#          过滤噪声标签后回写 problem.json 的 tags 字段（幂等，可重复执行）
#       2. 对已导入的题（按标题匹配 Problem）同步更新 tags，
#          并保证每个标签名在 tags 表有实例（缺失自动创建）
# 用法: cd api && .venv/Scripts/python.exe ../loj_import/scripts/sync_loj_tags.py [--dirs 1,100,102] [--dry-run]
# =============================================================

import argparse
import asyncio
import json
import sys
from pathlib import Path

# 容器内 app 包在 /app/app/，本地开发在 ../api/app/
_app_root = Path(__file__).resolve().parents[2]
if not (_app_root / "app" / "__init__.py").exists():
    _app_root = _app_root / "api"
sys.path.insert(0, str(_app_root))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import httpx
from sqlalchemy import func, select

from app.database import AsyncSessionLocal
from app.models import Problem, Tag
from fetch_loj_problems import HEADERS, fetch_tags_map  # 同目录兄弟模块

IMPORT_ROOT = Path(__file__).resolve().parents[1] / "data"


async def main() -> None:
    parser = argparse.ArgumentParser(description="补齐 LOJ 爬取产物标签并同步题库")
    parser.add_argument("--dirs", type=str, default="",
                        help="仅处理指定目录名（LOJ 题号，逗号分隔），默认全部")
    parser.add_argument("--dry-run", action="store_true", help="只打印将要做的事，不落库/不写文件")
    args = parser.parse_args()
    wanted = {s.strip() for s in args.dirs.split(",") if s.strip()}

    # —— 收集各目录的 problem.json ——
    entries: list[tuple[Path, dict, int]] = []  # (目录, problem.json内容, LOJ题号)
    for d in sorted(IMPORT_ROOT.iterdir()):
        if not d.is_dir() or not (d / "problem.json").is_file():
            continue
        if wanted and d.name not in wanted:
            continue
        pj = json.loads((d / "problem.json").read_text(encoding="utf-8"))
        try:
            loj_id = int(d.name)
        except ValueError:
            print(f"- 跳过 {d.name}：目录名不是 LOJ 题号")
            continue
        entries.append((d, pj, loj_id))
    if not entries:
        print("没有可处理的目录")
        return

    # —— 批量拉标签（列表接口翻页） ——
    async with httpx.AsyncClient(verify=True, headers=HEADERS) as client:
        tag_map = await fetch_tags_map(client, {e[2] for e in entries})

    # —— 回写 problem.json + 同步 DB ——
    async with AsyncSessionLocal() as db:
        for d, pj, loj_id in entries:
            names = tag_map.get(loj_id, [])
            print(f"LOJ #{loj_id} 《{pj['title']}》 → 标签 {names or '（无/仅噪声标签）'}")
            if not args.dry_run and pj.get("tags") != names:
                pj["tags"] = names
                (d / "problem.json").write_text(
                    json.dumps(pj, ensure_ascii=False, indent=1), encoding="utf-8")

            p = await db.scalar(select(Problem).where(Problem.title == pj["title"]))
            if p is None:
                continue  # 未导入，标签留在 problem.json 等导入脚本带上
            if args.dry_run:
                if p.tags != names:
                    print(f"  DB #{p.display_id} tags 将更新为 {names}")
                continue
            if p.tags != names:
                p.tags = names
            # tags 表实例兜底：题目用到的每个标签名都要有实例
            existing = set((await db.scalars(select(Tag.name))).all())
            for n in names:
                if n not in existing:
                    db.add(Tag(name=n))
                    existing.add(n)
                    print(f"  + tags 表新建实例「{n}」")
            await db.commit()
            print(f"  DB #{p.display_id} tags = {p.tags}")

        total = await db.scalar(select(func.count()).select_from(Tag))
        print(f"tags 表现有 {total} 个实例")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    asyncio.run(main())
