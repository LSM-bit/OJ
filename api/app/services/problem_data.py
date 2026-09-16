# =============================================================
# 文件: api/app/services/problem_data.py
# 用途: 题目测试数据 / 用户头像的存储抽象层，双后端可切换：
#       - MinioStore（默认，生产）：MinIO 对象存储
#           oj-problems 桶: {problem_id}-{data_version}/manifest.json + cases/*.in/.out
#           oj-avatars 桶:  u{user_id}.{ext}
#       - LocalStore（pytest 用）：本地文件系统 data/problems/ 同结构目录
# 对上层统一暴露模块级 async 原语（read_manifest / write_files / iter_files 等），
# 调用方不感知后端；MinIO SDK 为同步实现，统一经 asyncio.to_thread 包装。
# =============================================================

import json
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Protocol

from app.config import settings

CHUNK_SIZE = 256 * 1024


class Store(Protocol):
    """存储后端协议：题目数据包按目录语义整体读写"""

    async def read(self, problem_id: str, data_version: str, rel: str) -> bytes | None:
        """读单个文件，不存在返回 None"""
        ...

    async def exists(self, problem_id: str, data_version: str, rel: str) -> bool: ...
    async def write(self, problem_id: str, data_version: str, files: dict[str, bytes]) -> None:
        """整体替换某版本数据（先删旧前缀再写新对象）"""
        ...

    async def iter_all(self, problem_id: str, data_version: str) -> AsyncIterator[tuple[str, bytes]]:
        """遍历某版本全部文件，产出 (相对路径, 内容)"""
        ...

    async def list_file_sizes(self, problem_id: str, data_version: str) -> dict[str, int]:
        """列某版本全部文件的 {相对路径: 字节数}——只取元数据，零下载
        （出题者助手 get_problem_full 的数据强度统计用）"""
        ...


# ---------------- MinIO 后端 ----------------

class MinioStore:
    """MinIO 实现：目录语义 = 对象 key 前缀 {problem_id}-{data_version}/"""

    def __init__(self) -> None:
        from minio import Minio

        self._client = Minio(
            settings.minio_endpoint,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            secure=settings.minio_secure,
        )
        self._bucket = settings.minio_bucket_problems

    async def _ensure_bucket(self) -> None:
        def _create():
            if not self._client.bucket_exists(self._bucket):
                self._client.make_bucket(self._bucket)
        import asyncio
        await asyncio.to_thread(_create)

    def _key(self, problem_id: str, data_version: str, rel: str) -> str:
        return f"{problem_id}-{data_version}/{rel}"

    async def read(self, problem_id: str, data_version: str, rel: str) -> bytes | None:
        from minio.error import S3Error

        await self._ensure_bucket()
        import asyncio

        def _get() -> bytes:
            resp = self._client.get_object(self._bucket, self._key(problem_id, data_version, rel))
            try:
                return resp.read()
            finally:
                resp.close()
                resp.release_conn()
        try:
            return await asyncio.to_thread(_get)
        except S3Error as e:
            if e.code == "NoSuchKey":
                return None
            raise

    async def exists(self, problem_id: str, data_version: str, rel: str) -> bool:
        from minio.error import S3Error

        await self._ensure_bucket()
        import asyncio

        def _stat():
            self._client.stat_object(self._bucket, self._key(problem_id, data_version, rel))
        try:
            await asyncio.to_thread(_stat)
            return True
        except S3Error as e:
            if e.code == "NoSuchKey":
                return False
            raise

    async def write(self, problem_id: str, data_version: str, files: dict[str, bytes]) -> None:
        """整体替换：先清掉该版本前缀下的旧对象，再逐个 put。
        低频管理操作（上传数据包），不做增量 diff。"""
        import asyncio
        import io

        await self._ensure_bucket()
        prefix = f"{problem_id}-{data_version}/"

        def _replace():
            # 清旧（MinIO 无目录 rename，只能逐对象删）
            for obj in self._client.list_objects(self._bucket, prefix=prefix, recursive=True):
                self._client.remove_object(self._bucket, obj.object_name)
            for rel, content in files.items():
                self._client.put_object(
                    self._bucket, prefix + rel, io.BytesIO(content), length=len(content))
        await asyncio.to_thread(_replace)

    async def iter_all(self, problem_id: str, data_version: str) -> AsyncIterator[tuple[str, bytes]]:
        import asyncio

        await self._ensure_bucket()
        prefix = f"{problem_id}-{data_version}/"

        def _list() -> list[str]:
            return sorted(o.object_name for o in
                          self._client.list_objects(self._bucket, prefix=prefix, recursive=True))
        keys = await asyncio.to_thread(_list)
        for key in keys:
            def _get(k=key) -> bytes:
                resp = self._client.get_object(self._bucket, k)
                try:
                    return resp.read()
                finally:
                    resp.close()
                    resp.release_conn()
            yield key.removeprefix(prefix), await asyncio.to_thread(_get)

    async def list_file_sizes(self, problem_id: str, data_version: str) -> dict[str, int]:
        import asyncio

        await self._ensure_bucket()
        prefix = f"{problem_id}-{data_version}/"

        def _sizes() -> dict[str, int]:
            return {o.object_name.removeprefix(prefix): o.size
                    for o in self._client.list_objects(self._bucket, prefix=prefix, recursive=True)}
        return await asyncio.to_thread(_sizes)


# ---------------- 本地文件系统后端（pytest / 无 MinIO 环境兜底） ----------------

class LocalStore:
    """本地目录实现，与 MinioStore 同语义；目录结构一期遗留：
    {problem_data_dir}/{problem_id}-{data_version}/{rel}"""

    def _root(self, problem_id: str, data_version: str) -> Path:
        return Path(settings.problem_data_dir) / f"{problem_id}-{data_version}"

    async def read(self, problem_id: str, data_version: str, rel: str) -> bytes | None:
        f = self._root(problem_id, data_version) / rel
        return f.read_bytes() if f.is_file() else None

    async def exists(self, problem_id: str, data_version: str, rel: str) -> bool:
        return (self._root(problem_id, data_version) / rel).is_file()

    async def write(self, problem_id: str, data_version: str, files: dict[str, bytes]) -> None:
        """整体替换：tmp 目录写 + 校验 + rename 原子替换"""
        import shutil

        root = self._root(problem_id, data_version)
        tmp = root.with_name(root.name + ".tmp")
        if tmp.exists():
            shutil.rmtree(tmp)
        tmp.mkdir(parents=True)
        for rel, content in files.items():
            dest = tmp / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(content)
        if root.exists():
            shutil.rmtree(root)
        tmp.rename(root)

    async def iter_all(self, problem_id: str, data_version: str) -> AsyncIterator[tuple[str, bytes]]:
        root = self._root(problem_id, data_version)
        if not root.is_dir():
            return
        for file in sorted(root.rglob("*")):
            if file.is_file():
                yield file.relative_to(root).as_posix(), file.read_bytes()

    async def list_file_sizes(self, problem_id: str, data_version: str) -> dict[str, int]:
        import asyncio

        def _sizes() -> dict[str, int]:
            root = self._root(problem_id, data_version)
            if not root.is_dir():
                return {}
            return {f.relative_to(root).as_posix(): f.stat().st_size
                    for f in sorted(root.rglob("*")) if f.is_file()}
        return await asyncio.to_thread(_sizes)


def _store() -> Store:
    """按配置分派后端（简单 if，不值得上注册表）"""
    return MinioStore() if settings.storage_backend == "minio" else LocalStore()


# ---------------- 题目数据：模块级 async 原语 ----------------

async def read_file(problem_id: str, data_version: str, rel: str) -> bytes | None:
    return await _store().read(problem_id, data_version, rel)


async def read_text_file(problem_id: str, data_version: str, rel: str,
                         limit: int | None = None) -> str | None:
    """读文本（样例/用例预览用）；limit 截断字符数。文件缺失返回 None"""
    raw = await _store().read(problem_id, data_version, rel)
    if raw is None:
        return None
    text = raw.decode("utf-8", errors="replace")
    return text[:limit] if limit else text


async def read_manifest(problem_id: str, data_version: str) -> dict | None:
    """读 manifest.json；无数据返回 None"""
    raw = await _store().read(problem_id, data_version, "manifest.json")
    return json.loads(raw) if raw is not None else None


async def write_manifest(problem_id: str, data_version: str, manifest: dict) -> None:
    """只重写 manifest.json（用例重排等低频操作）"""
    await _store().write(
        problem_id, data_version,
        {"manifest.json": json.dumps(manifest, ensure_ascii=False).encode("utf-8")})


async def write_problem_data(problem_id: str, data_version: str, files: dict[str, bytes]) -> None:
    """出题人上传数据包时调用：整体替换某版本数据。
    manifest 合法性在内存中先校验（MinIO 无目录 rename 的原子替换，
    逐对象覆盖属低频管理操作，可接受）。"""
    manifest = json.loads(files["manifest.json"])
    for case in manifest["cases"]:
        assert f"cases/{case['id']}.in" in files, f"缺少 {case['id']}.in"
        assert f"cases/{case['id']}.out" in files, f"缺少 {case['id']}.out"
    await _store().write(problem_id, data_version, files)


def pack_cases(files: dict[str, bytes], sample_ids: set[str] | None = None) -> dict[str, bytes]:
    """从任意文件字典（.in/.out 可放根目录或 cases/ 子目录）提取成对用例，
    生成存储格式的完整数据包：{"cases/{stem}.in": ..., "manifest.json": ...}。
    - 非用例文件（manifest.json/readme 等杂物）一律丢弃——上传方无需提供 json；
    - 排序用自然序（tc2 在 tc10 前）；
    - 样例判定：sample_ids 指定则以其为准，否则 stem 以 "sample" 开头视为样例（score=0）；
    - 隐藏用例平分 100 分，余数补给第一个隐藏用例；全样例时分值均为 0；
    - 无成对用例抛 ValueError（调用方转 400）。
    纯函数，同步。"""
    import re

    def natural_key(stem: str) -> list:
        return [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", stem.lower())]

    ins: dict[str, bytes] = {}
    outs: dict[str, bytes] = {}
    for rel, content in files.items():
        base = rel.rsplit("/", 1)[-1]
        if base.endswith(".in"):
            stem, dest = base[:-3], ins
        elif base.endswith(".out"):
            stem, dest = base[:-4], outs
        else:
            continue
        if stem and re.fullmatch(r"[\w.\-]+", stem):
            dest[stem] = content
    paired = sorted(set(ins) & set(outs), key=natural_key)
    if not paired:
        raise ValueError("数据包中没有成对的 .in/.out 用例文件")

    is_sample = ((lambda s: s in sample_ids) if sample_ids is not None
                 else (lambda s: s.lower().startswith("sample")))
    hidden = [s for s in paired if not is_sample(s)]
    packed: dict[str, bytes] = {}
    manifest_cases = []
    for s in paired:
        score = 0 if is_sample(s) else (round(100 / len(hidden)) if hidden else 0)
        packed[f"cases/{s}.in"] = ins[s]
        packed[f"cases/{s}.out"] = outs[s]
        manifest_cases.append({"id": s, "score": score, "sample": is_sample(s)})
    if hidden:
        drift = 100 - sum(c["score"] for c in manifest_cases)
        if drift:
            manifest_cases[paired.index(hidden[0])]["score"] += drift
    packed["manifest.json"] = json.dumps({"cases": manifest_cases}, ensure_ascii=False).encode("utf-8")
    return packed


async def append_files(problem_id: str, data_version: str, extra: dict[str, bytes]) -> None:
    """增量覆盖部分文件（追加样例用例时：新 .in/.out + 重写后的 manifest）"""
    merged: dict[str, bytes] = {}
    async for rel, content in _store().iter_all(problem_id, data_version):
        merged[rel] = content
    merged.update(extra)
    await _store().write(problem_id, data_version, merged)


async def iter_problem_data(problem_id: str, data_version: str) -> AsyncIterator[tuple[str, bytes]]:
    """遍历题目数据，产出 (相对路径, 内容)。网关 FetchProblemData 分块下发用；
    目录/前缀不存在时产出空。"""
    async for item in _store().iter_all(problem_id, data_version):
        yield item


async def list_file_sizes(problem_id: str, data_version: str) -> dict[str, int]:
    """{相对路径: 字节数}，只读元数据不下载内容。数据不存在返回空 dict。"""
    return await _store().list_file_sizes(problem_id, data_version)


# ---------------- 用户头像（固定走 MinIO；local 后端下同样落 MinIO 桶，见 _avatar_store） ----------------

def _avatar_bucket() -> str:
    return settings.minio_bucket_avatars


def _avatar_client():
    from minio import Minio

    return Minio(
        settings.minio_endpoint,
        access_key=settings.minio_access_key,
        secret_key=settings.minio_secret_key,
        secure=settings.minio_secure,
    )


async def put_avatar(filename: str, data: bytes) -> None:
    """上传/覆盖头像对象"""
    import asyncio
    import io

    c = _avatar_client()

    def _put():
        if not c.bucket_exists(_avatar_bucket()):
            c.make_bucket(_avatar_bucket())
        c.put_object(_avatar_bucket(), filename, io.BytesIO(data), length=len(data))
    await asyncio.to_thread(_put)


async def get_avatar(filename: str) -> bytes | None:
    """读头像对象；不存在返回 None"""
    import asyncio

    from minio.error import S3Error

    c = _avatar_client()

    def _get() -> bytes:
        resp = c.get_object(_avatar_bucket(), filename)
        try:
            return resp.read()
        finally:
            resp.close()
            resp.release_conn()
    try:
        return await asyncio.to_thread(_get)
    except S3Error as e:
        if e.code == "NoSuchKey":
            return None
        raise


async def delete_avatar(filename: str) -> None:
    """删除头像对象（不存在时静默）"""
    import asyncio

    c = _avatar_client()
    await asyncio.to_thread(c.remove_object, _avatar_bucket(), filename)


# ---------------- 开发/自测辅助 ----------------

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
