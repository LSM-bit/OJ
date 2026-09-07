"""题目数据本地缓存：{problem_id}-{data_version} 目录 + manifest 判定"""

import os
from pathlib import Path


class ProblemDataCache:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self._in_use: set[str] = set()

    def dir_for(self, problem_id: str, data_version: str) -> Path:
        return self.root / f"{problem_id}-{data_version}"

    def has(self, problem_id: str, data_version: str) -> bool:
        hit = (self.dir_for(problem_id, data_version) / "manifest.json").is_file()
        if hit:
            os.utime(self.dir_for(problem_id, data_version), None)  # 刷新 LRU 时间
        return hit

    def mark_in_use(self, dir_name: str) -> None:
        self._in_use.add(dir_name)

    def unmark_in_use(self, dir_name: str) -> None:
        self._in_use.discard(dir_name)

    async def sync(self, problem_id: str, data_version: str, chunk_stream) -> Path:
        """消费网关 FetchProblemData 的 FileChunk 流写入本地"""
        target = self.dir_for(problem_id, data_version)
        if self.has(problem_id, data_version):
            return target
        tmp = target.with_name(target.name + ".tmp")
        tmp.mkdir(parents=True, exist_ok=True)
        count = 0
        try:
            async for chunk in chunk_stream:
                dest = tmp / chunk.path
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(chunk.content)
                count += 1
            if count == 0 or not (tmp / "manifest.json").exists():
                raise RuntimeError("题目数据流为空或缺少 manifest.json")
            tmp.rename(target)
        finally:
            if tmp.exists():
                import shutil
                shutil.rmtree(tmp, ignore_errors=True)
        return target
