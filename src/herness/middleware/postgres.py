"""Postgres 中台实现 — 持久化记忆、信念、任务结果与 Dreaming 队列。"""

from __future__ import annotations

import json
from importlib.resources import files
from typing import Any

from herness.middleware.beliefs import match_beliefs
from herness.middleware.memory import PreSynthesizedMemory, SynthesizedMemorySlice
from herness.models.worker import WorkerOutput


class PostgresMiddleware:
    """基于 asyncpg 的 DataMiddleware 实现。"""

    def __init__(self, dsn: str, *, auto_migrate: bool = True) -> None:
        self._dsn = dsn
        self._auto_migrate = auto_migrate
        self._pool: Any = None

    async def connect(self) -> None:
        """建立连接池并可选执行 schema 迁移。"""
        try:
            import asyncpg
        except ImportError as exc:
            raise ImportError(
                "PostgresMiddleware 需要 asyncpg，请安装: pip install 'herness-agent[postgres]'"
            ) from exc

        self._pool = await asyncpg.create_pool(self._dsn, min_size=1, max_size=10)
        if self._auto_migrate:
            await self._ensure_schema()

    async def close(self) -> None:
        """关闭连接池。"""
        if self._pool is not None:
            await self._pool.close()
            self._pool = None

    async def _ensure_schema(self) -> None:
        schema_sql = files("herness.middleware").joinpath("schema.sql").read_text(encoding="utf-8")
        async with self._pool.acquire() as conn:
            await conn.execute(schema_sql)

    # ── 只读接口（Worker / Critic 可用）──

    async def get_task_context(self, user_id: str, task_id: str) -> dict[str, Any]:
        row = await self._pool.fetchrow(
            "SELECT context FROM task_contexts WHERE task_id = $1 AND user_id = $2",
            task_id,
            user_id,
        )
        if row is None:
            return {
                "user_id": user_id,
                "task_id": task_id,
                "note": "任务级上下文（Worker 不可见全局记忆）",
            }
        context = row["context"]
        if isinstance(context, str):
            context = json.loads(context)
        return dict(context)

    async def query_beliefs(self, user_id: str, claims: list[str]) -> list[dict[str, Any]]:
        rows = await self._pool.fetch(
            "SELECT fact, source, confidence FROM beliefs WHERE user_id = $1 ORDER BY id",
            user_id,
        )
        user_beliefs = [
            {"fact": row["fact"], "source": row["source"], "confidence": row["confidence"]}
            for row in rows
        ]
        return match_beliefs(user_beliefs, claims)

    # ── 读写接口（仅调度器/总管）──

    async def get_pre_synthesized_memory(self, user_id: str) -> PreSynthesizedMemory:
        row = await self._pool.fetchrow(
            "SELECT user_id, version, summary, slices FROM memories WHERE user_id = $1",
            user_id,
        )
        if row is None:
            return PreSynthesizedMemory(user_id=user_id, summary="（尚未生成记忆）")

        raw_slices = row["slices"] or []
        if isinstance(raw_slices, str):
            raw_slices = json.loads(raw_slices)
        slices = [SynthesizedMemorySlice.model_validate(item) for item in raw_slices]
        return PreSynthesizedMemory(
            user_id=row["user_id"],
            summary=row["summary"],
            slices=slices,
            version=row["version"],
        )

    async def write_task_result(
        self,
        user_id: str,
        task_id: str,
        worker_output: WorkerOutput,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        payload = worker_output.model_dump(mode="json")
        meta = metadata or {}
        await self._pool.execute(
            """
            INSERT INTO task_results (task_id, user_id, output, metadata)
            VALUES ($1, $2, $3::jsonb, $4::jsonb)
            ON CONFLICT (task_id) DO UPDATE
            SET output = EXCLUDED.output,
                metadata = EXCLUDED.metadata
            """,
            task_id,
            user_id,
            json.dumps(payload),
            json.dumps(meta),
        )

    async def enqueue_dreaming_job(self, user_id: str, task_id: str) -> None:
        await self._pool.execute(
            """
            INSERT INTO dreaming_jobs (user_id, task_id, status)
            VALUES ($1, $2, 'pending')
            """,
            user_id,
            task_id,
        )

    async def get_task_result(self, user_id: str, task_id: str) -> WorkerOutput | None:
        row = await self._pool.fetchrow(
            "SELECT output FROM task_results WHERE task_id = $1 AND user_id = $2",
            task_id,
            user_id,
        )
        if row is None:
            return None
        output = row["output"]
        if isinstance(output, str):
            output = json.loads(output)
        return WorkerOutput.model_validate(output)

    async def save_pre_synthesized_memory(self, memory: PreSynthesizedMemory) -> None:
        await self.seed_memory(
            memory.user_id,
            memory.summary,
            memory.slices,
            version=memory.version,
        )

    async def dequeue_dreaming_job(self, *, timeout: int = 0) -> tuple[str, str] | None:
        """原子出队一条 pending 任务；timeout>0 时在超时前轮询。"""
        import asyncio

        poll = 0.2
        deadline = asyncio.get_running_loop().time() + timeout if timeout > 0 else None
        while True:
            row = await self._pool.fetchrow(
                """
                UPDATE dreaming_jobs
                SET status = 'processing'
                WHERE id = (
                    SELECT id FROM dreaming_jobs
                    WHERE status = 'pending'
                    ORDER BY id
                    LIMIT 1
                    FOR UPDATE SKIP LOCKED
                )
                RETURNING user_id, task_id
                """
            )
            if row is not None:
                return row["user_id"], row["task_id"]
            if deadline is None:
                return None
            if asyncio.get_running_loop().time() >= deadline:
                return None
            await asyncio.sleep(poll)

    async def mark_dreaming_job_done(
        self,
        user_id: str,
        task_id: str,
        *,
        success: bool = True,
    ) -> None:
        status = "done" if success else "failed"
        await self._pool.execute(
            """
            UPDATE dreaming_jobs
            SET status = $3
            WHERE user_id = $1 AND task_id = $2
            """,
            user_id,
            task_id,
            status,
        )

    # ── 数据维护（测试 / 管理用）──

    async def seed_memory(
        self,
        user_id: str,
        summary: str,
        slices: list[SynthesizedMemorySlice] | None = None,
        *,
        version: int = 1,
    ) -> None:
        slice_payload = [s.model_dump(mode="json") for s in (slices or [])]
        await self._pool.execute(
            """
            INSERT INTO memories (user_id, version, summary, slices, updated_at)
            VALUES ($1, $2, $3, $4::jsonb, NOW())
            ON CONFLICT (user_id) DO UPDATE
            SET version = EXCLUDED.version,
                summary = EXCLUDED.summary,
                slices = EXCLUDED.slices,
                updated_at = NOW()
            """,
            user_id,
            version,
            summary,
            json.dumps(slice_payload),
        )

    async def seed_belief(
        self,
        user_id: str,
        fact: str,
        source: str = "manual",
        confidence: float = 1.0,
    ) -> None:
        await self._pool.execute(
            """
            INSERT INTO beliefs (user_id, fact, source, confidence)
            VALUES ($1, $2, $3, $4)
            """,
            user_id,
            fact,
            source,
            confidence,
        )

    async def pending_dreaming_jobs(self) -> list[tuple[str, str]]:
        rows = await self._pool.fetch(
            """
            SELECT user_id, task_id FROM dreaming_jobs
            WHERE status = 'pending'
            ORDER BY id
            """
        )
        return [(row["user_id"], row["task_id"]) for row in rows]
