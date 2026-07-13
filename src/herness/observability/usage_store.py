"""Token 用量持久化 — 按任务记录，按 session / user 汇总查询。"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from importlib.resources import files
from typing import Any, Protocol, runtime_checkable

from herness.models.task import TaskStatus, TokenUsage

logger = logging.getLogger(__name__)

DEFAULT_USAGE_SOURCE = "orchestrator"


def usage_schema_sql() -> str:
    """usage_events 表 DDL — 与 middleware/schema.sql 共用同一文件。"""
    return files("herness.observability").joinpath("usage_schema.sql").read_text(encoding="utf-8")


def usage_schema_comments_sql() -> str:
    """usage_events 表与字段注释 SQL。"""
    return files("herness.observability").joinpath("usage_schema_comments.sql").read_text(
        encoding="utf-8"
    )


USAGE_SCHEMA = usage_schema_sql()


@dataclass
class UsageEvent:
    """单任务 token 用量记录。"""

    task_id: str
    user_id: str
    session_id: str
    source: str
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
        source: str = DEFAULT_USAGE_SOURCE,
    ) -> None: ...

    async def get_session_usage(self, user_id: str, session_id: str) -> TokenUsage: ...

    async def get_user_usage(self, user_id: str) -> TokenUsage: ...

    async def close(self) -> None: ...


def _apply_usage_delta(target: TokenUsage, usage: TokenUsage, *, sign: int = 1) -> None:
    """对汇总桶做加减；sign=-1 用于 upsert 时撤销旧值。"""
    target.input_tokens += sign * usage.input_tokens
    target.output_tokens += sign * usage.output_tokens
    target.requests += sign * usage.requests
    target.tool_calls += sign * usage.tool_calls
    target.total_tokens = target.input_tokens + target.output_tokens


class InMemoryUsageStore:
    """进程内用量存储（无 Postgres 时使用）。"""

    def __init__(self) -> None:
        self._by_task: dict[tuple[str, str], UsageEvent] = {}
        self._session_totals: dict[tuple[str, str], TokenUsage] = {}
        self._user_totals: dict[str, TokenUsage] = {}

    def _task_key(self, task_id: str, source: str) -> tuple[str, str]:
        return (task_id, source)

    def _session_key(self, user_id: str, session_id: str) -> tuple[str, str]:
        return (user_id, session_id)

    def _adjust_totals(
        self,
        user_id: str,
        session_id: str,
        usage: TokenUsage,
        *,
        sign: int,
    ) -> None:
        session_total = self._session_totals.setdefault(
            self._session_key(user_id, session_id),
            TokenUsage(),
        )
        user_total = self._user_totals.setdefault(user_id, TokenUsage())
        for bucket in (session_total, user_total):
            _apply_usage_delta(bucket, usage, sign=sign)

    async def record_task_usage(
        self,
        *,
        task_id: str,
        user_id: str,
        session_id: str,
        status: TaskStatus,
        usage: TokenUsage,
        source: str = DEFAULT_USAGE_SOURCE,
    ) -> None:
        key = self._task_key(task_id, source)
        previous = self._by_task.get(key)
        if previous is not None:
            self._adjust_totals(
                previous.user_id,
                previous.session_id,
                previous.usage,
                sign=-1,
            )
        usage_copy = usage.model_copy()
        self._by_task[key] = UsageEvent(
            task_id=task_id,
            user_id=user_id,
            session_id=session_id,
            source=source,
            status=status,
            usage=usage_copy,
        )
        self._adjust_totals(user_id, session_id, usage_copy, sign=1)

    async def get_session_usage(self, user_id: str, session_id: str) -> TokenUsage:
        total = self._session_totals.get(self._session_key(user_id, session_id))
        return total.model_copy() if total is not None else TokenUsage()

    async def get_user_usage(self, user_id: str) -> TokenUsage:
        total = self._user_totals.get(user_id)
        return total.model_copy() if total is not None else TokenUsage()

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
            await conn.execute(usage_schema_comments_sql())

    async def record_task_usage(
        self,
        *,
        task_id: str,
        user_id: str,
        session_id: str,
        status: TaskStatus,
        usage: TokenUsage,
        source: str = DEFAULT_USAGE_SOURCE,
    ) -> None:
        if self._pool is None:
            raise RuntimeError("PostgresUsageStore 未 connect")
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO usage_events (
                    task_id, user_id, session_id, source, status,
                    input_tokens, output_tokens, total_tokens, requests, tool_calls
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                ON CONFLICT (task_id, source) DO UPDATE SET
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
                source,
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
