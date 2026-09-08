"""添加示例题目：输入 A，输出 A（A+B Problem 变体）

用法: .venv/Scripts/python -m app.scripts.seed_example_problem
功能: 创建一个简单的示例题目，用于测试判题系统
"""

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models import Problem, Testcase, User, UserRole
from app.services.problem_data import put_example_data

# 示例题目配置
EXAMPLE_PROBLEM = {
    "display_id": 1001,
    "title": "A+B Problem",
    "description": """# A+B Problem

## 题目描述

输入两个整数 $a$ 和 $b$，输出它们的和 $a + b$。

## 输入格式

一行两个整数 $a, b$，用空格分隔。

## 输出格式

一行一个整数，表示 $a + b$ 的值。

## 样例

**输入:**
```
1 2
```

**输出:**
```
3
```

## 数据范围

- $-10^9 \\le a, b \\le 10^9$
- 时间限制: 1 秒
- 内存限制: 256 MB
""",
    "difficulty": 1,
    "tags": ["入门", "模拟"],
    "config": {
        "time_limit_ms": 1000,
        "memory_limit_mb": 256,
        "languages": ["python3.12", "cpp17", "c17", "java21"],
    },
}

# 测试用例：输入 A，输出 A（实际是输入两个数，输出和）
TEST_CASES = [
    ("tc0", "1 2\n", "3\n", 30),
    ("tc1", "100 200\n", "300\n", 30),
    ("tc2", "-1 1\n", "0\n", 40),
]


async def seed_example_problem() -> None:
    """添加示例题目"""
    async with AsyncSessionLocal() as db:
        # 检查题目是否已存在
        existing = await db.scalar(
            select(Problem).where(Problem.display_id == EXAMPLE_PROBLEM["display_id"])
        )
        if existing:
            print(f"题目 {EXAMPLE_PROBLEM['display_id']} 已存在，跳过创建")
            return

        # 获取管理员用户作为出题人
        admin = await db.scalar(select(User).where(User.role == UserRole.ADMIN))
        if not admin:
            print("错误: 未找到管理员用户，请先运行 create_admin 脚本")
            return

        # 创建题目
        problem = Problem(
            display_id=EXAMPLE_PROBLEM["display_id"],
            title=EXAMPLE_PROBLEM["title"],
            description=EXAMPLE_PROBLEM["description"],
            difficulty=EXAMPLE_PROBLEM["difficulty"],
            tags=EXAMPLE_PROBLEM["tags"],
            config=EXAMPLE_PROBLEM["config"],
            owner_id=admin.id,
            is_public=True,
        )
        db.add(problem)
        await db.commit()
        await db.refresh(problem)

        # 添加测试用例到数据库
        for idx, (case_id, _, _, score) in enumerate(TEST_CASES):
            testcase = Testcase(
                problem_id=problem.id,
                idx=idx,
                case_id=case_id,
                input_key=f"cases/{case_id}.in",
                output_key=f"cases/{case_id}.out",
                score=score,
            )
            db.add(testcase)

        await db.commit()

        # 写入测试数据文件
        await put_example_data(
            str(problem.id),
            [(case_id, inp, out, score) for case_id, inp, out, score in TEST_CASES],
        )

        print(f"[OK] Example problem created:")
        print(f"  Problem ID: {problem.display_id}")
        print(f"  Title: {problem.title}")
        print(f"  DB ID: {problem.id}")
        print(f"  Test cases: {len(TEST_CASES)}")
        print(f"  Data dir: api/data/problems/{problem.id}-v1/")


if __name__ == "__main__":
    asyncio.run(seed_example_problem())
