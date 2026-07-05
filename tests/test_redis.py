"""Redis 队列与缓存单元测试 — 使用 fakeredis。"""

import pytest

fakeredis = pytest.importorskip("fakeredis")

from herness.middleware.memory import PreSynthesizedMemory, SynthesizedMemorySlice
from herness.middleware.redis_augment import RedisAugmentedMiddleware
from herness.middleware.stub import InMemoryMiddleware
from herness.redis.cache import MemoryCache
from herness.redis.queue import DreamingQueue


@pytest.fixture
async def fake_redis():
    client = fakeredis.aioredis.FakeRedis(decode_responses=True)
    yield client
    await client.aclose()


async def test_dreaming_queue_fifo(fake_redis) -> None:
    queue = DreamingQueue(fake_redis)
    await queue.enqueue("u1", "t1")
    await queue.enqueue("u2", "t2")

    assert await queue.length() == 2
    assert await queue.pending() == [("u1", "t1"), ("u2", "t2")]
    assert await queue.dequeue(timeout=1) == ("u1", "t1")
    assert await queue.dequeue(timeout=1) == ("u2", "t2")


async def test_memory_cache_skips_empty(fake_redis) -> None:
    cache = MemoryCache(fake_redis, ttl_seconds=60)
    empty = PreSynthesizedMemory(user_id="u1", summary="（尚未生成记忆）")
    await cache.set(empty)
    assert await cache.get("u1") is None

    memory = PreSynthesizedMemory(
        user_id="u1",
        summary="有内容",
        slices=[SynthesizedMemorySlice(category="facts", content="x")],
    )
    await cache.set(memory)
    cached = await cache.get("u1")
    assert cached is not None
    assert cached.summary == "有内容"

    await cache.invalidate("u1")
    assert await cache.get("u1") is None


async def test_redis_augmented_middleware(fake_redis) -> None:
    inner = InMemoryMiddleware()
    inner.seed_memory("u1", "缓存测试")

    middleware = RedisAugmentedMiddleware(inner, "redis://unused", memory_ttl_seconds=60)
    middleware._redis = fake_redis
    middleware._queue = DreamingQueue(fake_redis)
    middleware._memory_cache = MemoryCache(fake_redis, ttl_seconds=60)

    memory1 = await middleware.get_pre_synthesized_memory("u1")
    assert memory1.summary == "缓存测试"

    inner.seed_memory("u1", "不应读到")
    memory2 = await middleware.get_pre_synthesized_memory("u1")
    assert memory2.summary == "缓存测试"

    await middleware.enqueue_dreaming_job("u1", "task-1")
    assert await middleware.pending_dreaming_jobs() == [("u1", "task-1")]
