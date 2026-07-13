"""Postgres 中台实现 — 持久化记忆、信念、任务结果与 Dreaming 队列。"""



from __future__ import annotations



import json
import logging

from importlib.resources import files

from typing import Any



from herness.middleware.beliefs import extract_search_terms, match_beliefs, resolve_belief_write_conflict

from herness.middleware.embeddings import EmbeddingClient

from herness.middleware.memory import PreSynthesizedMemory, SynthesizedMemorySlice

from herness.middleware.session import SessionHistoryEntry

from herness.models.worker import WorkerOutput

from herness.rag.models import RagSearchResult

from herness.rag.pipeline import RagPipeline

from herness.rag.store.postgres import PostgresKnowledgeStore





class PostgresMiddleware:

    """基于 asyncpg 的 DataMiddleware 实现。"""



    def __init__(

        self,

        dsn: str,

        *,

        auto_migrate: bool = True,

        settings: Any = None,

        hereness_enabled: bool = False,

        hereness_vector_enabled: bool = False,

        embedding_client: EmbeddingClient | None = None,

        embedding_dimensions: int = 1536,

        hereness_vector_top_k: int = 10,

        hereness_vector_min_similarity: float = 0.5,

        hereness_conflict_decay_factor: float = 0.5,

        hereness_superseded_threshold: float = 0.3,

    ) -> None:

        self._dsn = dsn

        self._auto_migrate = auto_migrate

        self._settings = settings

        self._hereness_enabled = hereness_enabled

        self._hereness_vector_enabled = hereness_vector_enabled

        self._rag_vector_enabled = bool(
            settings and getattr(settings, "rag_vector_enabled", False)
        )

        self._embedding_client = embedding_client

        self._embedding_dimensions = embedding_dimensions

        self._hereness_vector_top_k = hereness_vector_top_k

        self._hereness_vector_min_similarity = hereness_vector_min_similarity

        self._hereness_conflict_decay_factor = hereness_conflict_decay_factor

        self._hereness_superseded_threshold = hereness_superseded_threshold

        self._pool: Any = None

        self._kb_store: PostgresKnowledgeStore | None = None

        self._rag_pipeline: RagPipeline | None = None



    async def connect(self) -> None:

        """建立连接池并可选执行 schema 迁移。"""

        try:

            import asyncpg

        except ImportError as exc:

            raise ImportError(

                "PostgresMiddleware 需要 asyncpg，请安装: pip install 'herness-agent[postgres]'"

            ) from exc



        self._pool = await asyncpg.create_pool(

            self._dsn,

            min_size=1,

            max_size=10,

        )

        if self._auto_migrate:

            await self._ensure_schema()

            need_vector = self._hereness_vector_enabled or self._rag_vector_enabled

            if need_vector:

                vector_ready = await self._ensure_vector_schema()

                if not vector_ready:

                    self._hereness_vector_enabled = False

                    self._rag_vector_enabled = False



        need_vector_pool = self._hereness_vector_enabled or self._rag_vector_enabled

        if need_vector_pool:

            await self._pool.close()

            self._pool = None



            async def _init_connection(conn: Any) -> None:

                from pgvector.asyncpg import register_vector



                await register_vector(conn)



            self._pool = await asyncpg.create_pool(

                self._dsn,

                min_size=1,

                max_size=10,

                init=_init_connection,

            )



        if self._settings and getattr(self._settings, "rag_enabled", False):

            self._kb_store = PostgresKnowledgeStore(

                self._pool,

                embedding_dimensions=self._embedding_dimensions,

                vector_enabled=self._rag_vector_enabled,

            )

            rag_vector_ready = await self._kb_store.ensure_schema()

            if not rag_vector_ready:

                self._rag_vector_enabled = False

            self._rag_pipeline = RagPipeline(

                self._kb_store,

                self._settings,

                embedding_client=self._embedding_client,

            )



    async def close(self) -> None:

        """关闭连接池。"""

        if self._pool is not None:

            await self._pool.close()

            self._pool = None



    async def _ensure_schema(self) -> None:

        from herness.observability.usage_store import usage_schema_comments_sql, usage_schema_sql

        schema_sql = files("herness.middleware").joinpath("schema.sql").read_text(encoding="utf-8")
        comments_sql = files("herness.middleware").joinpath("schema_comments.sql").read_text(
            encoding="utf-8"
        )
        schema_sql = f"{schema_sql.rstrip()}\n\n{usage_schema_sql()}"

        async with self._pool.acquire() as conn:

            await conn.execute(schema_sql)
            await conn.execute(comments_sql)
            await conn.execute(usage_schema_comments_sql())



    async def _ensure_vector_schema(self) -> bool:

        """按配置维度创建 fact_embedding 列与 HNSW 索引；pgvector 不可用时返回 False。"""

        logger = logging.getLogger(__name__)

        dim = self._embedding_dimensions

        async with self._pool.acquire() as conn:

            try:

                await conn.execute("CREATE EXTENSION IF NOT EXISTS vector")

            except Exception as exc:

                logger.warning(

                    "pgvector 扩展不可用，已禁用 Hereness 向量检索: %s",

                    exc,

                )

                return False

            try:

                await conn.execute(

                    f"""

                ALTER TABLE beliefs

                ADD COLUMN IF NOT EXISTS fact_embedding vector({dim})

                """

                )

                await conn.execute(

                    """

                CREATE INDEX IF NOT EXISTS idx_beliefs_fact_embedding

                ON beliefs USING hnsw (fact_embedding vector_cosine_ops)

                """

                )

                await conn.execute(

                    "COMMENT ON COLUMN beliefs.fact_embedding IS "

                    "'信念语义向量（pgvector，用于 Hereness 相似度检索）'"

                )

            except Exception as exc:

                logger.warning(

                    "向量列/索引创建失败，已禁用 Hereness 向量检索: %s",

                    exc,

                )

                return False

        return True



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

        if self._hereness_enabled:

            return await self._query_beliefs_deep(user_id, claims)



        rows = await self._pool.fetch(

            "SELECT id, fact, source, confidence, status FROM beliefs WHERE user_id = $1 AND status = 'active' ORDER BY id",

            user_id,

        )

        user_beliefs = [

            {

                "id": row["id"],

                "fact": row["fact"],

                "source": row["source"],

                "confidence": row["confidence"],

                "status": row["status"],

            }

            for row in rows

        ]

        return match_beliefs(user_beliefs, claims)



    async def search_knowledge_base(

        self,

        query: str,

        *,

        collection_id: str = "default",

        user_id: str = "",

    ) -> RagSearchResult:

        if self._rag_pipeline is None:

            return RagSearchResult(query=query, collection_id=collection_id, hits=[])

        return await self._rag_pipeline.search(
            query,
            collection_id=collection_id,
            user_id=user_id,
        )



    @property

    def knowledge_store(self) -> PostgresKnowledgeStore | None:

        return self._kb_store



    async def _query_beliefs_deep(self, user_id: str, claims: list[str]) -> list[dict[str, Any]]:

        """Hereness 深度检索 — FTS + 可选 pgvector 语义检索。"""

        results: list[dict[str, Any]] = []

        for claim in claims:

            matches = await self._search_beliefs_for_claim(user_id, claim)

            results.extend(match_beliefs(matches, [claim], deep=True))

        return results



    async def _search_beliefs_for_claim(

        self,

        user_id: str,

        claim: str,

    ) -> list[dict[str, Any]]:

        terms = extract_search_terms(claim)

        fts_matches = await self._fts_search_beliefs(user_id, claim, terms)

        merged: dict[str, dict[str, Any]] = {item["fact"]: item for item in fts_matches}



        if self._hereness_vector_enabled and self._embedding_client is not None:

            vector_matches = await self._vector_search_beliefs(user_id, claim)

            for item in vector_matches:

                fact = item["fact"]

                if fact in merged:

                    merged[fact]["vector_similarity"] = max(

                        merged[fact].get("vector_similarity", 0.0),

                        item.get("vector_similarity", 0.0),

                    )

                else:

                    merged[fact] = item



        ranked = sorted(

            merged.values(),

            key=lambda item: (

                item.get("vector_similarity", 0.0),

                item.get("fts_rank", 0.0),

                item.get("confidence", 0.0),

            ),

            reverse=True,

        )

        return ranked[: self._hereness_vector_top_k]



    async def _fts_search_beliefs(

        self,

        user_id: str,

        claim: str,

        terms: list[str],

    ) -> list[dict[str, Any]]:

        rows = await self._pool.fetch(

            """

            SELECT id, fact, source, confidence, status,

                   ts_rank(fact_tsv, plainto_tsquery('simple', $2)) AS fts_rank

            FROM beliefs

            WHERE user_id = $1

              AND status = 'active'

              AND (

                  fact_tsv @@ plainto_tsquery('simple', $2)

                  OR fact ILIKE '%' || $2 || '%'

                  OR (

                      cardinality($3::text[]) > 0

                      AND EXISTS (

                          SELECT 1 FROM unnest($3::text[]) AS t(term)

                          WHERE fact ILIKE '%' || term || '%'

                      )

                  )

              )

            ORDER BY fts_rank DESC NULLS LAST, confidence DESC

            LIMIT $4

            """,

            user_id,

            claim,

            terms,

            self._hereness_vector_top_k,

        )

        return [

            {

                "id": row["id"],

                "fact": row["fact"],

                "source": row["source"],

                "confidence": row["confidence"],

                "status": row["status"],

                "fts_rank": float(row["fts_rank"] or 0.0),

            }

            for row in rows

        ]



    async def _vector_search_beliefs(

        self,

        user_id: str,

        claim: str,

    ) -> list[dict[str, Any]]:

        if self._embedding_client is None:

            return []



        query_vector = await self._embedding_client.embed_one(claim, user_id=user_id)

        rows = await self._pool.fetch(

            """

            SELECT id, fact, source, confidence, status,

                   1 - (fact_embedding <=> $2::vector) AS vector_similarity

            FROM beliefs

            WHERE user_id = $1

              AND status = 'active'

              AND fact_embedding IS NOT NULL

              AND 1 - (fact_embedding <=> $2::vector) >= $3

            ORDER BY fact_embedding <=> $2::vector

            LIMIT $4

            """,

            user_id,

            query_vector,

            self._hereness_vector_min_similarity,

            self._hereness_vector_top_k,

        )

        return [

            {

                "id": row["id"],

                "fact": row["fact"],

                "source": row["source"],

                "confidence": row["confidence"],

                "status": row["status"],

                "vector_similarity": float(row["vector_similarity"]),

            }

            for row in rows

        ]



    async def _embed_fact(self, fact: str, *, user_id: str) -> list[float] | None:

        if not self._hereness_vector_enabled or self._embedding_client is None:

            return None

        return await self._embedding_client.embed_one(fact, user_id=user_id)



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



    async def get_session_history(

        self,

        session_id: str,

        *,

        exclude_task_id: str | None = None,

        limit: int = 5,

        persona: str | None = None,

    ) -> list[SessionHistoryEntry]:

        """读取同 session 的前序任务摘要（按时间正序）。"""

        rows = await self._pool.fetch(

            """

            SELECT task_id, output, metadata, created_at

            FROM task_results

            WHERE metadata->>'session_id' = $1

              AND ($2::text IS NULL OR task_id != $2)

              AND ($4::text IS NULL OR metadata->>'persona' = $4)

            ORDER BY created_at DESC

            LIMIT $3

            """,

            session_id,

            exclude_task_id,

            limit,

            persona,

        )



        entries: list[SessionHistoryEntry] = []

        for row in reversed(rows):

            output_data = row["output"]

            if isinstance(output_data, str):

                output_data = json.loads(output_data)

            output = WorkerOutput.model_validate(output_data)



            meta = row["metadata"] or {}

            if isinstance(meta, str):

                meta = json.loads(meta)



            answer = meta.get("final_answer") or output.summary or output.content

            entries.append(

                SessionHistoryEntry(

                    task_id=row["task_id"],

                    input=str(meta.get("input", "")),

                    answer=str(answer),

                    created_at=row["created_at"],

                )

            )

        return entries



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



    async def get_task_metadata(self, user_id: str, task_id: str) -> dict[str, Any]:

        row = await self._pool.fetchrow(

            "SELECT metadata FROM task_results WHERE task_id = $1 AND user_id = $2",

            task_id,

            user_id,

        )

        if row is None:

            return {}

        metadata = row["metadata"]

        if isinstance(metadata, str):

            metadata = json.loads(metadata)

        if not isinstance(metadata, dict):

            return {}

        return dict(metadata)



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



    async def _fetch_active_beliefs(self, user_id: str) -> list[dict[str, Any]]:

        rows = await self._pool.fetch(

            """

            SELECT id, fact, source, confidence, status

            FROM beliefs

            WHERE user_id = $1 AND status = 'active'

            ORDER BY id

            """,

            user_id,

        )

        return [

            {

                "id": row["id"],

                "fact": row["fact"],

                "source": row["source"],

                "confidence": row["confidence"],

                "status": row["status"],

            }

            for row in rows

        ]



    async def _apply_belief_updates(self, updates: list[dict[str, Any]]) -> None:

        for update in updates:

            belief_id = update["id"]

            if "confidence" in update and "status" in update:

                await self._pool.execute(

                    "UPDATE beliefs SET confidence = $2, status = $3 WHERE id = $1",

                    belief_id,

                    update["confidence"],

                    update["status"],

                )

            elif "confidence" in update:

                await self._pool.execute(

                    "UPDATE beliefs SET confidence = $2 WHERE id = $1",

                    belief_id,

                    update["confidence"],

                )

            elif "status" in update:

                await self._pool.execute(

                    "UPDATE beliefs SET status = $2 WHERE id = $1",

                    belief_id,

                    update["status"],

                )



    async def seed_belief(

        self,

        user_id: str,

        fact: str,

        source: str = "manual",

        confidence: float = 1.0,

    ) -> None:

        adjusted = confidence

        status = "active"

        if self._hereness_enabled:

            existing = await self._fetch_active_beliefs(user_id)

            adjusted, status, updates = resolve_belief_write_conflict(

                fact,

                confidence,

                existing,

                decay_factor=self._hereness_conflict_decay_factor,

                superseded_threshold=self._hereness_superseded_threshold,

            )

            await self._apply_belief_updates(updates)



        embedding = await self._embed_fact(fact, user_id=user_id)

        if embedding is not None:

            await self._pool.execute(

                """

                INSERT INTO beliefs (user_id, fact, source, confidence, status, fact_embedding)

                VALUES ($1, $2, $3, $4, $5, $6::vector)

                """,

                user_id,

                fact,

                source,

                adjusted,

                status,

                embedding,

            )

            return



        await self._pool.execute(

            """

            INSERT INTO beliefs (user_id, fact, source, confidence, status)

            VALUES ($1, $2, $3, $4, $5)

            """,

            user_id,

            fact,

            source,

            adjusted,

            status,

        )



    async def backfill_belief_embeddings(self, user_id: str | None = None) -> int:

        """为缺失 fact_embedding 的信念补写向量（运维 / 迁移用）。"""

        if not self._hereness_vector_enabled or self._embedding_client is None:

            return 0



        if user_id is None:

            rows = await self._pool.fetch(

                """

                SELECT id, fact FROM beliefs

                WHERE fact_embedding IS NULL

                ORDER BY id

                """

            )

        else:

            rows = await self._pool.fetch(

                """

                SELECT id, fact FROM beliefs

                WHERE user_id = $1 AND fact_embedding IS NULL

                ORDER BY id

                """,

                user_id,

            )



        updated = 0

        for row in rows:

            embedding = await self._embedding_client.embed_one(row["fact"], user_id=user_id)

            await self._pool.execute(

                """

                UPDATE beliefs SET fact_embedding = $2::vector WHERE id = $1

                """,

                row["id"],

                embedding,

            )

            updated += 1

        return updated



    async def pending_dreaming_jobs(self) -> list[tuple[str, str]]:

        rows = await self._pool.fetch(

            """

            SELECT user_id, task_id FROM dreaming_jobs

            WHERE status = 'pending'

            ORDER BY id

            """

        )

        return [(row["user_id"], row["task_id"]) for row in rows]


