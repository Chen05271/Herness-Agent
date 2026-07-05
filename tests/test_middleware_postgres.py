"""PostgresMiddleware 集成测试 — 需 POSTGRES_TEST_DSN 环境变量。"""

import os
import uuid

import pytest

from herness.middleware.memory import SynthesizedMemorySlice
from herness.middleware.postgres import PostgresMiddleware
from herness.models.worker import WorkerOutput

POSTGRES_TEST_DSN = os.getenv("POSTGRES_TEST_DSN", "")
pytestmark = pytest.mark.skipif(
    not POSTGRES_TEST_DSN,
    reason="未设置 POSTGRES_TEST_DSN，跳过 Postgres 集成测试",
)


@pytest.fixture
async def pg_mw() -> PostgresMiddleware:
    middleware = PostgresMiddleware(POSTGRES_TEST_DSN)
    await middleware.connect()
    yield middleware
    await middleware.close()


async def test_postgres_memory_and_beliefs_persist(pg_mw: PostgresMiddleware) -> None:
    """记忆与信念写入后，重连仍可读取。"""
    user_id = f"test_user_{uuid.uuid4().hex[:8]}"
    await pg_mw.seed_memory(
        user_id,
        "持久化摘要",
        [SynthesizedMemorySlice(category="facts", content="测试事实")],
    )
    await pg_mw.seed_belief(user_id, "Herness Agent 支持 Postgres")

    memory = await pg_mw.get_pre_synthesized_memory(user_id)
    assert memory.summary == "持久化摘要"
    assert len(memory.slices) == 1

    beliefs = await pg_mw.query_beliefs(user_id, ["Herness Agent"])
    assert beliefs[0]["status"] == "supported"

    await pg_mw.close()
    reconnected = PostgresMiddleware(POSTGRES_TEST_DSN)
    await reconnected.connect()
    try:
        memory2 = await reconnected.get_pre_synthesized_memory(user_id)
        assert memory2.summary == "持久化摘要"
        beliefs2 = await reconnected.query_beliefs(user_id, ["Herness Agent"])
        assert beliefs2[0]["status"] == "supported"
    finally:
        await reconnected.close()


async def test_postgres_task_result_and_dreaming_queue(pg_mw: PostgresMiddleware) -> None:
    user_id = f"test_user_{uuid.uuid4().hex[:8]}"
    task_id = str(uuid.uuid4())
    output = WorkerOutput(content="结果", summary="完成")

    await pg_mw.write_task_result(user_id, task_id, output)
    await pg_mw.enqueue_dreaming_job(user_id, task_id)

    queue = await pg_mw.pending_dreaming_jobs()
    assert (user_id, task_id) in queue


async def test_postgres_default_memory(pg_mw: PostgresMiddleware) -> None:
    memory = await pg_mw.get_pre_synthesized_memory(f"unknown_{uuid.uuid4().hex}")
    assert "尚未生成记忆" in memory.summary
