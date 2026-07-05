"""Dreaming 任务队列 — Redis List。"""

from __future__ import annotations

import json
from typing import Any

from herness.redis.keys import DREAMING_QUEUE


class DreamingQueue:
    """LPUSH / BRPOP 实现的 Dreaming 队列。"""

    def __init__(self, redis_client: Any, *, key: str = DREAMING_QUEUE) -> None:
        self._redis = redis_client
        self._key = key

    async def enqueue(self, user_id: str, task_id: str) -> None:
        payload = json.dumps({"user_id": user_id, "task_id": task_id}, ensure_ascii=False)
        await self._redis.lpush(self._key, payload)

    async def dequeue(self, *, timeout: int = 0) -> tuple[str, str] | None:
        """阻塞出队；timeout=0 表示一直等待。"""
        result = await self._redis.brpop(self._key, timeout=timeout)
        if result is None:
            return None
        _, payload = result
        data = json.loads(payload)
        return data["user_id"], data["task_id"]

    async def pending(self) -> list[tuple[str, str]]:
        """按 FIFO 顺序返回队列中全部待处理任务。"""
        items = await self._redis.lrange(self._key, 0, -1)
        jobs: list[tuple[str, str]] = []
        for payload in reversed(items):
            data = json.loads(payload)
            jobs.append((data["user_id"], data["task_id"]))
        return jobs

    async def length(self) -> int:
        return int(await self._redis.llen(self._key))
