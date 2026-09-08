# -*- coding: utf-8 -*-
# 文件: api/tests/test_problem_cases.py
# 用途: 题目用例管理接口测试：用例列表/追加样例/删除重排/撤回下架（含权限边界）

import pytest
from httpx import AsyncClient

from tests.conftest import auth_header, make_user, setup_public_problem

pytestmark = pytest.mark.asyncio


async def _create_draft(client, user, title="用例题") -> dict:
    r = await client.post("/problems", json={"title": title, "description": "d"},
                          headers=await auth_header(user))
    assert r.status_code == 201, r.text
    return r.json()


async def test_cases_list_after_upload(client, normal_user, gateway):
    """上传数据后用例列表正确分组（manifest 带 sample 标记）"""
    import io
    import json
    import zipfile

    p = await _create_draft(client, normal_user)
    manifest = {"cases": [{"id": "s0", "score": 0, "sample": True},
                          {"id": "h0", "score": 100}]}
    files = {"manifest.json": json.dumps(manifest).encode(),
             "cases/s0.in": b"1 2", "cases/s0.out": b"3",
             "cases/h0.in": b"5 5", "cases/h0.out": b"10"}
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, content in files.items():
            zf.writestr(name, content)
    r = await client.post(f"/problems/{p['id']}/data",
                          files={"file": ("d.zip", buf.getvalue(), "application/zip")},
                          headers=await auth_header(normal_user))
    assert r.status_code == 200, r.text

    r = await client.get(f"/problems/{p['id']}/cases",
                         headers=await auth_header(normal_user))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["has_data"] is True
    assert [s["case_id"] for s in body["samples"]] == ["s0"]
    assert [c["case_id"] for c in body["cases"]] == ["h0"]


async def test_add_sample_case(client, normal_user, gateway):
    """追加样例：落盘 + testcases 同步 + 详情下发样例"""
    p = await _create_draft(client, normal_user)
    r = await client.post(f"/problems/{p['id']}/cases/sample",
                          json={"input": "3 4", "output": "7", "is_sample": True},
                          headers=await auth_header(normal_user))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["case_id"] == "tc0"
    assert body["is_sample"] is True

    # 再加一个隐藏用例
    r = await client.post(f"/problems/{p['id']}/cases/sample",
                          json={"input": "0 0", "output": "0"},
                          headers=await auth_header(normal_user))
    assert r.json()["is_sample"] is False

    # 详情（题面）只见样例
    r = await client.get(f"/problems/{p['id']}", headers=await auth_header(normal_user))
    samples = r.json()["samples"]
    assert len(samples) == 1
    assert samples[0]["input"] == "3 4"


async def test_delete_case_and_reorder(client, normal_user):
    """删除用例后 idx 重排"""
    p = await _create_draft(client, normal_user)
    for i in range(3):
        r = await client.post(f"/problems/{p['id']}/cases/sample",
                              json={"input": f"{i}", "output": f"{i}"},
                              headers=await auth_header(normal_user))
        assert r.status_code == 200

    # 删除中间一个
    r = await client.delete(f"/problems/{p['id']}/cases/1",
                            headers=await auth_header(normal_user))
    assert r.status_code == 200, r.text
    assert r.json()["count"] == 2

    r = await client.get(f"/problems/{p['id']}/cases",
                         headers=await auth_header(normal_user))
    body = r.json()
    all_cases = body["samples"] + body["cases"]
    assert [c["idx"] for c in all_cases] == [0, 1]

    # 删除不存在的 idx
    r = await client.delete(f"/problems/{p['id']}/cases/99",
                            headers=await auth_header(normal_user))
    assert r.status_code == 404


async def test_cases_requires_manage(client, normal_user, db_sessionmaker, gateway):
    """用例管理接口：非 owner 不可操作"""
    p = await _create_draft(client, normal_user)
    async with db_sessionmaker() as db:
        other = await make_user(db, "case_stranger")

    r = await client.get(f"/problems/{p['id']}/cases",
                         headers=await auth_header(other))
    assert r.status_code == 404  # 防枚举

    r = await client.post(f"/problems/{p['id']}/cases/sample",
                          json={"input": "1", "output": "1"},
                          headers=await auth_header(other))
    assert r.status_code == 404


async def test_unpublish_withdraws_problem(client, normal_user, gateway, db_sessionmaker):
    """发布后可撤回（is_public=false），撤回后匿名不可见"""
    p = await setup_public_problem(client, normal_user, title="撤回题")

    r = await client.get(f"/problems/{p['id']}")  # 匿名可见
    assert r.status_code == 200

    r = await client.put(f"/problems/{p['id']}/publish", json={"is_public": False},
                         headers=await auth_header(normal_user))
    assert r.status_code == 200, r.text
    assert r.json()["is_public"] is False

    r = await client.get(f"/problems/{p['id']}")  # 匿名不可见
    assert r.status_code == 404

    # 重新公开仍受验证凭证保护（verified_at 仍在）→ 可直接发布
    r = await client.put(f"/problems/{p['id']}/publish", json={"is_public": True},
                         headers=await auth_header(normal_user))
    assert r.status_code == 200, r.text


async def test_publish_blocked_after_data_change(client, normal_user, gateway):
    """重新上传数据后验证凭证作废，直接发布被拒"""
    import io
    import json
    import zipfile

    p = await setup_public_problem(client, normal_user, title="凭证作废题")

    # 重新上传数据（verified_at 被清空）
    manifest = {"cases": [{"id": "tc0", "score": 100}]}
    files = {"manifest.json": json.dumps(manifest).encode(),
             "cases/tc0.in": b"9 9", "cases/tc0.out": b"18"}
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, content in files.items():
            zf.writestr(name, content)
    r = await client.post(f"/problems/{p['id']}/data",
                          files={"file": ("d.zip", buf.getvalue(), "application/zip")},
                          headers=await auth_header(normal_user))
    assert r.status_code == 200

    r = await client.put(f"/problems/{p['id']}/publish", json={"is_public": False},
                         headers=await auth_header(normal_user))
    assert r.status_code == 200

    # 无验证凭证 → 不能再公开
    r = await client.put(f"/problems/{p['id']}/publish", json={"is_public": True},
                         headers=await auth_header(normal_user))
    assert r.status_code == 400, r.text
    assert "标程验证" in r.json()["detail"]
