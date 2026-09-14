# =============================================================
# 文件: api/app/scripts/migrate_problem_data_to_minio.py
# 用途: 一次性迁移脚本——把本地 data/problems/ 存量数据包搬进 MinIO
#       （write_problem_data 幂等覆盖，可重复执行）
# 用法: cd api && python -m app.scripts.migrate_problem_data_to_minio
# =============================================================

import asyncio
import sys
from pathlib import Path

# 脚本直跑时补 sys.path（与 seed_example_problem.py 同套路）
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from app.config import settings


async def main() -> None:
    root = Path(settings.problem_data_dir)
    if not root.is_dir():
        print(f"本地数据目录不存在: {root.resolve()}，无事可做")
        return

    # 后端必须是 minio，否则迁移无意义
    if settings.storage_backend != "minio":
        print(f"当前 storage_backend={settings.storage_backend}，请设为 minio 后再迁移")
        sys.exit(1)

    from app.services.problem_data import write_problem_data

    total = 0
    for pkg_dir in sorted(p for p in root.iterdir() if p.is_dir()):
        files = {f.relative_to(pkg_dir).as_posix(): f.read_bytes()
                 for f in pkg_dir.rglob("*") if f.is_file()}
        if "manifest.json" not in files:
            print(f"跳过 {pkg_dir.name}: 缺少 manifest.json")
            continue
        # 目录名 {problem_id}-{data_version} → 拆回两段（版本 = 最后一个 '-' 之后）
        stem, _, version = pkg_dir.name.rpartition("-")
        await write_problem_data(stem, version, files)
        total += 1
        print(f"已迁移 {pkg_dir.name}: {len(files)} 个文件")
    print(f"完成，共迁移 {total} 个数据包")


if __name__ == "__main__":
    asyncio.run(main())
