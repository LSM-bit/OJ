"""题目测试数据服务

一期：本地文件系统 data/problems/{problem_id}-{data_version}/
  ├── manifest.json          # {"cases": [{"id": "tc0", "score": 10}]}
  └── cases/tc0.in / tc0.out
生产（二期）：换对象存储实现同一 iter_problem_data 接口。
"""

import json
from pathlib import Path
from typing import AsyncIterator

from app.config import settings

CHUNK_SIZE = 256 * 1024


def data_dir(problem_id: str, data_version: str) -> Path:
    return Path(settings.problem_data_dir) / f"{problem_id}-{data_version}"


async def iter_problem_data(problem_id: str, data_version: str) -> AsyncIterator[tuple[str, bytes]]:
    """遍历题目数据目录，产出 (相对路径, 内容)。目录不存在时产出空。"""
    root = data_dir(problem_id, data_version)
    if not root.is_dir():
        return
    for file in sorted(root.rglob("*")):
        if file.is_file():
            rel = file.relative_to(root).as_posix()
            yield rel, file.read_bytes()


async def write_problem_data(problem_id: str, data_version: str, files: dict[str, bytes]) -> None:
    """出题人上传数据包时调用：整体替换某版本数据。"""
    import shutil

    root = data_dir(problem_id, data_version)
    tmp = root.with_name(root.name + ".tmp")
    if tmp.exists():
        shutil.rmtree(tmp)
    tmp.mkdir(parents=True)
    for rel, content in files.items():
        dest = tmp / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(content)
    # 校验 manifest 合法
    manifest = json.loads((tmp / "manifest.json").read_bytes())
    for case in manifest["cases"]:
        assert (tmp / "cases" / f"{case['id']}.in").is_file(), f"缺少 {case['id']}.in"
        assert (tmp / "cases" / f"{case['id']}.out").is_file(), f"缺少 {case['id']}.out"
    if root.exists():
        shutil.rmtree(root)
    tmp.rename(root)


async def put_example_data(
    problem_id: str, cases: list[tuple[str, str, str, int] | tuple[str, str, str]]
) -> None:
    """快速写入示例数据：cases = [(case_id, input, output, score?)]（开发/自测用）"""
    manifest = {"cases": [{"id": c[0], "score": (c[3] if len(c) > 3 else 10)} for c in cases]}
    files = {"manifest.json": json.dumps(manifest).encode()}
    for c in cases:
        cid, inp, out = c[0], c[1], c[2]
        files[f"cases/{cid}.in"] = inp.encode()
        files[f"cases/{cid}.out"] = out.encode()
    await write_problem_data(problem_id, "v1", files)
