"""Token 用量持久化 — 按任务记录，按 session / user 汇总查询。"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Protocol, runtime_checkable

from herness.models.task import TaskStatus, TokenUsage

logger = logging.getLogger(__name__)

USAGE_SCHEMA = """
CREATE TABLE IF NOT EXISTS usage_events (
    id BIGSERIAL PRIMARY KEY,
    task_id TEXT NOT NULL UNIQUE,
    user_id TEXT NOT NULL,
    session_id TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT '',
    input_tokens INT NOT NULL DEFAULT 0,
    output_tokens INT NOT NULL DEFAULT 0,
    total_tokens INT NOT NULL DEFAULT 0,
    requests INT NOT NULL DEFAULT 0,
    tool_calls INT NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_usage_events_session ON usage_events (session_id);
CREATE INDEX IF NOT EXISTS idx_usage_events_user ON usage_events (user_id);
CREATE INDEX IF NOT EXISTS idx_usage_events_created ON usage_events (created_at DESC);
"""


@dataclass
class UsageEvent:
    """单任务 token 用量记录。"""

    task_id: str
    user_id: str
    session_id: str
    status: TaskStatus
    usage: TokenUsage
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@runtime_checkable
class UsageStore(Protocol):
    """Token 用量存储协议。"""

    async def record_task_usage(
        self,
        *,
        task_id: str,
        user_id: str,
        session_id: str,
        status: TaskStatus,
        usage: TokenUsage,
    ) -> None: ...

    async def get_session_usage(self, user_id: str, session_id: str) -> TokenUsage: ...

    async def get_user_usage(self, user_id: str) -> TokenUsage: ...

    async def close(self) -> None: ...


def _sum_usage(events: list[UsageEvent]) -> TokenUsage:
    total = TokenUsage()
    for event in events:
        total.accumulate(event.usage)
    return total


class InMemoryUsageStore:
    """进程内用量存储（无 Postgres 时使用）。"""

    def __init__(self) -> None:
        self._events: list[UsageEvent] = []

    async def record_task_usage(
        self,
        *,
        task_id: str,
        user_id: str,
        session_id: str,
        status: TaskStatus,
        usage: TokenUsage,
    ) -> None:
        self._events = [e for e in self._events if e.task_id != task_id]
        self._events.append(
            UsageEvent(
                task_id=task_id,
                user_id=user_id,
                session_id=session_id,
                status=status,
                usage=usage.model_copy(),
            )
        )

    async def get_session_usage(self, user_id: str, session_id: str) -> TokenUsage:
        matched = [
            e
            for e in self._events
            if e.user_id == user_id and e.session_id == session_id
        ]
        return _sum_usage(matched)

    async def get_user_usage(self, user_id: str) -> TokenUsage:
        matched = [e for e in self._events if e.user_id == user_id]
        return _sum_usage(matched)

    async def close(self) -> None:
        return None


class PostgresUsageStore:
    """Postgres 持久化用量存储。"""

    def __init__(self, dsn: str) -> None:
        self._dsn = dsn
        self._pool: Any = None

    async def connect(self) -> None:
        import asyncpg

        self._pool = await asyncpg.create_pool(self._dsn, min_size=1, max_size=4)
        async with self._pool.acquire() as conn:
            await conn.execute(USAGE_SCHEMA)

    async def record_task_usage(
        self,
        *,
        task_id: str,
        user_id: str,
        session_id: str,
        status: TaskStatus,
        usage: TokenUsage,
    ) -> None:
        if self._pool is None:
            raise RuntimeError("PostgresUsageStore 未 connect")
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO usage_events (
                    task_id, user_id, session_id, status,
                    input_tokens, output_tokens, total_tokens, requests, tool_calls
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                ON CONFLICT (task_id) DO UPDATE SET
                    status = EXCLUDED.status,
                    input_tokens = EXCLUDED.input_tokens,
                    output_tokens = EXCLUDED.output_tokens,
                    total_tokens = EXCLUDED.total_tokens,
                    requests = EXCLUDED.requests,
                    tool_calls = EXCLUDED.tool_calls
                """,
                task_id,
                user_id,
                session_id,
                status.value,
                usage.input_tokens,
                usage.output_tokens,
                usage.total_tokens,
                usage.requests,
                usage.tool_calls,
            )

    async def _aggregate(self, where_sql: str, *args: object) -> TokenUsage:
        if self._pool is None:
            raise RuntimeError("PostgresUsageStore 未 connect")
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                f"""
                SELECT
                    COALESCE(SUM(input_tokens), 0) AS input_tokens,
                    COALESCE(SUM(output_tokens), 0) AS output_tokens,
                    COALESCE(SUM(total_tokens), 0) AS total_tokens,
                    COALESCE(SUM(requests), 0) AS requests,
                    COALESCE(SUM(tool_calls), 0) AS tool_calls
                FROM usage_events
                WHERE {where_sql}
                """,
                *args,
            )
        if row is None:
            return TokenUsage()
        return TokenUsage(
            input_tokens=int(row["input_tokens"]),
            output_tokens=int(row["output_tokens"]),
            total_tokens=int(row["total_tokens"]),
            requests=int(row["requests"]),
            tool_calls=int(row["tool_calls"]),
        )

    async def get_session_usage(self, user_id: str, session_id: str) -> TokenUsage:
        return await self._aggregate(
            "user_id = $1 AND session_id = $2",
            user_id,
            session_id,
        )

    async def get_user_usage(self, user_id: str) -> TokenUsage:
        return await self._aggregate("user_id = $1", user_id)

    async def close(self) -> None:
        if self._pool is not None:
            await self._pool.close()
            self._pool = None


async def create_usage_store(settings: Any) -> UsageStore:
    """按配置创建用量存储。"""
    if settings.postgres_dsn:
        store = PostgresUsageStore(settings.postgres_dsn)
        await store.connect()
        return store
    return InMemoryUsageStore()


async def close_usage_store(store: UsageStore | None) -> None:
    if store is not None:
        await store.close()
