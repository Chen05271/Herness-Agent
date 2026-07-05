"""Redis 增强层 — 为任意中台实现挂载队列与记忆缓存。"""

from __future__ import annotations

from typing import Any

from herness.middleware.memory import PreSynthesizedMemory
from herness.models.worker import WorkerOutput
from herness.redis.cache import EMPTY_MEMORY_MARKER, MemoryCache
from herness.redis.client import close_async_redis, create_async_redis
from herness.redis.queue import DreamingQueue


class RedisAugmentedMiddleware:
    """装饰式 Redis 层：Dreaming 队列 + 记忆热缓存。"""

    def __init__(
        self,
        inner: Any,
        redis_url: str,
        *,
        memory_ttl_seconds: int = 3600,
    ) -> None:
        self._inner = inner
        self._redis_url = redis_url
        self._memory_ttl_seconds = memory_ttl_seconds
        self._redis: Any = None
        self._queue: DreamingQueue | None = None
        self._memory_cache: MemoryCache | None = None

    async def connect(self) -> None:
        self._redis = await create_async_redis(self._redis_url)
        self._queue = DreamingQueue(self._redis)
        self._memory_cache = MemoryCache(self._redis, ttl_seconds=self._memory_ttl_seconds)

    async def close(self) -> None:
        await close_async_redis(self._redis)
        self._redis = None
        self._queue = None
        self._memory_cache = None
        inner_close = getattr(self._inner, "close", None)
        if inner_close is not None:
            await inner_close()

    # ── 只读接口 ──

    async def get_task_context(self, user_id: str, task_id: str) -> dict[str, Any]:
        return await self._inner.get_task_context(user_id, task_id)

    async def query_beliefs(self, user_id: str, claims: list[str]) -> list[dict[str, Any]]:
        return await self._inner.query_beliefs(user_id, claims)

    # ── 读写接口 ──

    async def get_pre_synthesized_memory(self, user_id: str) -> PreSynthesizedMemory:
        assert self._memory_cache is not None
        cached = await self._memory_cache.get(user_id)
        if cached is not None:
            return cached

        memory = await self._inner.get_pre_synthesized_memory(user_id)
        if EMPTY_MEMORY_MARKER not in memory.summary or memory.slices:
            await self._memory_cache.set(memory)
        return memory

    async def write_task_result(
        self,
        user_id: str,
        task_id: str,
        worker_output: WorkerOutput,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        await self._inner.write_task_result(user_id, task_id, worker_output, metadata)

    async def enqueue_dreaming_job(self, user_id: str, task_id: str) -> None:
        assert self._queue is not None
        await self._queue.enqueue(user_id, task_id)

    # ── 调试 / 测试 / Worker 消费 ──

    async def pending_dreaming_jobs(self) -> list[tuple[str, str]]:
        assert self._queue is not None
        return await self._queue.pending()

    async def dequeue_dreaming_job(self, *, timeout: int = 0) -> tuple[str, str] | None:
        assert self._queue is not None
        return await self._queue.dequeue(timeout=timeout)

    async def invalidate_memory_cache(self, user_id: str) -> None:
        assert self._memory_cache is not None
        await self._memory_cache.invalidate(user_id)

    def __getattr__(self, name: str) -> Any:
        """其余方法（如 seed_memory）透传至内层实现。"""
        return getattr(self._inner, name)
