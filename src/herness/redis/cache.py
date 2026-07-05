"""Redis 热缓存 — 预合成记忆与任务状态。"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from herness.middleware.memory import PreSynthesizedMemory
from herness.models.task import TaskResult, TaskStatus
from herness.redis.keys import MEMORY_PREFIX, TASK_PREFIX

EMPTY_MEMORY_MARKER = "（尚未生成记忆）"


class MemoryCache:
    """用户预合成记忆缓存，减少 Postgres 读取。"""

    def __init__(self, redis_client: Any, *, ttl_seconds: int = 3600) -> None:
        self._redis = redis_client
        self._ttl = ttl_seconds

    def _key(self, user_id: str) -> str:
        return f"{MEMORY_PREFIX}{user_id}"

    async def get(self, user_id: str) -> PreSynthesizedMemory | None:
        raw = await self._redis.get(self._key(user_id))
        if raw is None:
            return None
        return PreSynthesizedMemory.model_validate_json(raw)

    async def set(self, memory: PreSynthesizedMemory) -> None:
        if EMPTY_MEMORY_MARKER in memory.summary and not memory.slices:
            return
        await self._redis.set(self._key(memory.user_id), memory.model_dump_json(), ex=self._ttl)

    async def invalidate(self, user_id: str) -> None:
        await self._redis.delete(self._key(user_id))


class TaskStatusCache:
    """任务状态短期缓存 — 供 RUNNING/COMPLETED 态快速查询。"""

    def __init__(self, redis_client: Any, *, ttl_seconds: int = 86400) -> None:
        self._redis = redis_client
        self._ttl = ttl_seconds

    def _key(self, task_id: str) -> str:
        return f"{TASK_PREFIX}{task_id}"

    async def get(self, task_id: str) -> dict[str, Any] | None:
        raw = await self._redis.get(self._key(task_id))
        if raw is None:
            return None
        return json.loads(raw)

    async def set(
        self,
        *,
        task_id: str,
        status: TaskStatus,
        answer: str = "",
        error: str = "",
        rounds_used: int = 0,
        created_at: datetime,
        updated_at: datetime,
        result: TaskResult | None = None,
    ) -> None:
        payload = {
            "task_id": task_id,
            "status": status.value,
            "answer": answer,
            "error": error,
            "rounds_used": rounds_used,
            "created_at": created_at.isoformat(),
            "updated_at": updated_at.isoformat(),
            "result": result.model_dump(mode="json") if result else None,
        }
        await self._redis.set(self._key(task_id), json.dumps(payload, ensure_ascii=False), ex=self._ttl)

    async def delete(self, task_id: str) -> None:
        await self._redis.delete(self._key(task_id))
