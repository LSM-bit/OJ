import sys, os, json, zipfile, asyncio, time, traceback
from pathlib import Path

sys.path.insert(0, '/app')

from sqlalchemy import func, select
from app.database import AsyncSessionLocal
from app.models import Problem, User, UserRole
from app.routers.problems import _sync_testcases_from_manifest
from app.services.problem_data import pack_cases, write_problem_data

IMPORT_ROOT = Path('/app/loj_import/data')
TOTAL = len([d for d in IMPORT_ROOT.iterdir() if d.is_dir() and (d / "problem.json").is_file()]) if IMPORT_ROOT.is_dir() else 0

def load_dir(d):
    pj = json.loads((d / "problem.json").read_text(encoding="utf-8"))
    with zipfile.ZipFile(d / "data.zip") as zf:
        files = {n: zf.read(n) for n in zf.namelist() if not n.endswith("/")}
    return pj, files

def sample_ids_of(files):
    raw = files.get("manifest.json")
    if not raw:
        return set()
    try:
        return {c["id"] for c in json.loads(raw)["cases"] if c.get("sample")}
    except (ValueError, KeyError, TypeError):
        return set()

async def main():
    print(f"开始导入: {TOTAL} 道题", flush=True)
    t0 = time.time()
    async with AsyncSessionLocal() as db:
        admin = await db.scalar(select(User).where(User.role == UserRole.ADMIN))
        if not admin:
            print("ERROR: 未找到管理员", flush=True)
            return
        print(f"管理员: id={admin.id}", flush=True)

        ok = skipped = failed = 0
        for idx, d in enumerate(sorted(IMPORT_ROOT.iterdir()), 1):
            if not d.is_dir() or not (d / "problem.json").is_file():
                continue
            tag = f"[{idx}/{TOTAL}] LOJ#{d.name}"
            try:
                pj, files = load_dir(d)
                exists = await db.scalar(select(Problem).where(Problem.title == pj["title"]))
                if exists:
                    skipped += 1
                    print(f"- {tag} 《{pj['title']}》 已存在(#{exists.display_id}) 跳过", flush=True)
                    continue
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
                        "source": pj.get("source", ""),
                        "data_version": "v1",
                    },
                    owner_id=admin.id,
                    is_public=True,
                )
                db.add(p)
                await db.commit()
                await db.refresh(p)

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
                ok += 1
                print(f"+ {tag} #{p.display_id} 《{pj['title']}》 成功({len(manifest['cases'])-n_sample}隐藏+{n_sample}样例) 总计:成功{ok} 跳过{skipped} 失败{failed}", flush=True)
            except Exception as exc:
                failed += 1
                print(f"! {tag} 失败: {exc}", flush=True)
                await db.rollback()
        print(f"=== 完成: 成功 {ok}, 跳过 {skipped}, 失败 {failed}, 耗时 {int(time.time()-t0)}s ===", flush=True)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception:
        traceback.print_exc()