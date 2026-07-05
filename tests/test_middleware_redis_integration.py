"""Redis 集成测试 — 需 REDIS_TEST_URL 环境变量。"""

import os
import uuid

import pytest

from herness.middleware.redis_augment import RedisAugmentedMiddleware
from herness.middleware.stub import InMemoryMiddleware

REDIS_TEST_URL = os.getenv("REDIS_TEST_URL", "")
pytestmark = pytest.mark.skipif(
    not REDIS_TEST_URL,
    reason="未设置 REDIS_TEST_URL，跳过 Redis 集成测试",
)


@pytest.fixture
async def redis_mw() -> RedisAugmentedMiddleware:
    inner = InMemoryMiddleware()
    middleware = RedisAugmentedMiddleware(inner, REDIS_TEST_URL)
    await middleware.connect()
    yield middleware
    await middleware.close()


async def test_redis_dreaming_queue_integration(redis_mw: RedisAugmentedMiddleware) -> None:
    user_id = f"user_{uuid.uuid4().hex[:8]}"
    task_id = str(uuid.uuid4())

    await redis_mw.enqueue_dreaming_job(user_id, task_id)
    pending = await redis_mw.pending_dreaming_jobs()
    assert (user_id, task_id) in pending

    dequeued = await redis_mw.dequeue_dreaming_job(timeout=1)
    assert dequeued == (user_id, task_id)
