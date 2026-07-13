"""PostgresUsageStore 集成测试 — 需 POSTGRES_TEST_DSN 环境变量。"""

import os
import uuid

import pytest

from herness.models.task import TaskStatus, TokenUsage
from herness.observability.usage_store import PostgresUsageStore

POSTGRES_TEST_DSN = os.getenv("POSTGRES_TEST_DSN", "")
pytestmark = pytest.mark.skipif(
    not POSTGRES_TEST_DSN,
    reason="未设置 POSTGRES_TEST_DSN，跳过 Postgres 集成测试",
)


@pytest.fixture
async def pg_usage_store() -> PostgresUsageStore:
    store = PostgresUsageStore(POSTGRES_TEST_DSN)
    await store.connect()
    yield store
    await store.close()


async def test_postgres_usage_store_session_aggregate(
    pg_usage_store: PostgresUsageStore,
) -> None:
    user_id = f"usage_user_{uuid.uuid4().hex[:8]}"
    session_id = f"usage_sess_{uuid.uuid4().hex[:8]}"
    first = TokenUsage(input_tokens=100, output_tokens=40, total_tokens=140, requests=1)
    second = TokenUsage(input_tokens=50, output_tokens=20, total_tokens=70, requests=1)

    await pg_usage_store.record_task_usage(
        task_id=str(uuid.uuid4()),
        user_id=user_id,
        session_id=session_id,
        status=TaskStatus.COMPLETED,
        usage=first,
    )
    await pg_usage_store.record_task_usage(
        task_id=str(uuid.uuid4()),
        user_id=user_id,
        session_id=session_id,
        status=TaskStatus.COMPLETED,
        usage=second,
    )

    session_usage = await pg_usage_store.get_session_usage(user_id, session_id)
    assert session_usage.total_tokens == 210
    assert session_usage.requests == 2

    user_usage = await pg_usage_store.get_user_usage(user_id)
    assert user_usage.total_tokens == 210


async def test_postgres_usage_store_upsert_and_multi_source(
    pg_usage_store: PostgresUsageStore,
) -> None:
    user_id = f"usage_user_{uuid.uuid4().hex[:8]}"
    session_id = f"usage_sess_{uuid.uuid4().hex[:8]}"
    task_id = str(uuid.uuid4())
    original = TokenUsage(input_tokens=100, output_tokens=40, total_tokens=140, requests=1)
    updated = TokenUsage(input_tokens=30, output_tokens=10, total_tokens=40, requests=1)
    dreaming = TokenUsage(input_tokens=20, output_tokens=5, total_tokens=25, requests=1)

    await pg_usage_store.record_task_usage(
        task_id=task_id,
        user_id=user_id,
        session_id=session_id,
        status=TaskStatus.COMPLETED,
        usage=original,
    )
    await pg_usage_store.record_task_usage(
        task_id=task_id,
        user_id=user_id,
        session_id=session_id,
        status=TaskStatus.COMPLETED,
        usage=updated,
    )
    await pg_usage_store.record_task_usage(
        task_id=task_id,
        user_id=user_id,
        session_id=session_id,
        status=TaskStatus.COMPLETED,
        usage=dreaming,
        source="dreaming",
    )

    session_usage = await pg_usage_store.get_session_usage(user_id, session_id)
    assert session_usage.total_tokens == 65
