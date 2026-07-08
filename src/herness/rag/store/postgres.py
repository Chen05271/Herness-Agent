"""Postgres 知识库存储。"""

from __future__ import annotations

import json
import logging
from typing import Any

from herness.middleware.beliefs import extract_search_terms
from herness.rag.grep.retrieval import build_grep_patterns

logger = logging.getLogger(__name__)


class PostgresKnowledgeStore:
    """基于 asyncpg 的知识库实现。"""

    def __init__(
        self,
        pool: Any,
        *,
        embedding_dimensions: int = 1024,
        vector_enabled: bool = False,
    ) -> None:
        self._pool = pool
        self._embedding_dimensions = embedding_dimensions
        self._vector_enabled = vector_enabled

    async def ensure_schema(self) -> bool:
        """创建 RAG 表与向量列；pgvector 不可用时禁用向量检索。"""
        async with self._pool.acquire() as conn:
            await conn.execute(_BASE_SCHEMA_SQL)

            if not self._vector_enabled:
                return True

            try:
                await conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
            except Exception as exc:
                logger.warning("RAG pgvector 不可用，已禁用向量检索: %s", exc)
                self._vector_enabled = False
                return False

            dim = self._embedding_dimensions
            await conn.execute(
                f"""
                ALTER TABLE kb_chunks
                ADD COLUMN IF NOT EXISTS embedding vector({dim})
                """
            )
            await conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_kb_chunks_embedding
                ON kb_chunks USING hnsw (embedding vector_cosine_ops)
                WHERE embedding IS NOT NULL
                """
            )
        return True

    async def fts_search(
        self,
        collection_id: str,
        query: str,
        *,
        limit: int,
        min_rank: float,
    ) -> list[dict[str, Any]]:
        rows = await self._pool.fetch(
            """
            SELECT id, collection_id, content, metadata, source,
                   ts_rank(content_tsv, plainto_tsquery('simple', $2)) AS fts_rank
            FROM kb_chunks
            WHERE collection_id = $1
              AND content_tsv @@ plainto_tsquery('simple', $2)
              AND ts_rank(content_tsv, plainto_tsquery('simple', $2)) >= $3
            ORDER BY fts_rank DESC
            LIMIT $4
            """,
            collection_id,
            query,
            min_rank,
            limit,
        )
        return [_row_to_chunk(row) for row in rows]

    async def grep_search(
        self,
        collection_id: str,
        query: str,
        *,
        limit: int,
    ) -> list[dict[str, Any]]:
        patterns = build_grep_patterns(query)
        if not patterns:
            return await self.fts_search(collection_id, query, limit=limit, min_rank=0.01)

        conditions = " OR ".join(f"content ILIKE ${i + 2}" for i in range(len(patterns)))
        sql = f"""
            SELECT id, collection_id, content, metadata, source, 0.0 AS fts_rank
            FROM kb_chunks
            WHERE collection_id = $1 AND ({conditions})
            LIMIT ${len(patterns) + 2}
        """
        rows = await self._pool.fetch(sql, collection_id, *patterns, limit)
        return [_row_to_chunk(row) for row in rows]

    async def vector_search(
        self,
        collection_id: str,
        query_vector: list[float],
        *,
        limit: int,
        min_similarity: float,
    ) -> list[dict[str, Any]]:
        if not self._vector_enabled:
            return []

        rows = await self._pool.fetch(
            """
            SELECT id, collection_id, content, metadata, source,
                   1 - (embedding <=> $2::vector) AS vector_similarity
            FROM kb_chunks
            WHERE collection_id = $1
              AND embedding IS NOT NULL
              AND 1 - (embedding <=> $2::vector) >= $3
            ORDER BY embedding <=> $2::vector
            LIMIT $4
            """,
            collection_id,
            query_vector,
            min_similarity,
            limit,
        )
        return [_row_to_chunk(row) for row in rows]

    async def get_chunks_by_ids(
        self,
        collection_id: str,
        chunk_ids: list[int],
    ) -> list[dict[str, Any]]:
        if not chunk_ids:
            return []
        rows = await self._pool.fetch(
            """
            SELECT id, collection_id, content, metadata, source
            FROM kb_chunks
            WHERE collection_id = $1 AND id = ANY($2::bigint[])
            """,
            collection_id,
            chunk_ids,
        )
        return [_row_to_chunk(row) for row in rows]

    async def list_entities(self, collection_id: str) -> list[dict[str, Any]]:
        rows = await self._pool.fetch(
            """
            SELECT name, entity_type, chunk_ids
            FROM kb_entities
            WHERE collection_id = $1
            """,
            collection_id,
        )
        return [
            {
                "name": row["name"],
                "entity_type": row["entity_type"],
                "chunk_ids": list(row["chunk_ids"] or []),
            }
            for row in rows
        ]

    async def list_edges(self, collection_id: str) -> list[dict[str, Any]]:
        rows = await self._pool.fetch(
            """
            SELECT e.source_name AS source, e.target_name AS target,
                   e.relation, e.chunk_id
            FROM kb_edges e
            WHERE e.collection_id = $1
            """,
            collection_id,
        )
        return [dict(row) for row in rows]

    async def list_communities(self, collection_id: str) -> list[dict[str, Any]]:
        rows = await self._pool.fetch(
            """
            SELECT community_id, summary, entity_names
            FROM kb_communities
            WHERE collection_id = $1
            ORDER BY community_id
            """,
            collection_id,
        )
        return [
            {
                "community_id": row["community_id"],
                "summary": row["summary"],
                "entity_names": list(row["entity_names"] or []),
            }
            for row in rows
        ]

    async def upsert_collection(
        self,
        collection_id: str,
        name: str,
        *,
        persona: str | None = None,
    ) -> None:
        await self._pool.execute(
            """
            INSERT INTO kb_collections (id, name, persona)
            VALUES ($1, $2, $3)
            ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name, persona = EXCLUDED.persona
            """,
            collection_id,
            name,
            persona,
        )

    async def insert_chunks(
        self,
        collection_id: str,
        chunks: list[dict[str, Any]],
    ) -> list[int]:
        ids: list[int] = []
        async with self._pool.acquire() as conn:
            for item in chunks:
                embedding = item.get("embedding")
                if embedding is not None and self._vector_enabled:
                    row = await conn.fetchrow(
                        """
                        INSERT INTO kb_chunks (collection_id, content, metadata, source, embedding)
                        VALUES ($1, $2, $3::jsonb, $4, $5::vector)
                        RETURNING id
                        """,
                        collection_id,
                        item["content"],
                        json.dumps(item.get("metadata", {})),
                        item.get("source", ""),
                        embedding,
                    )
                else:
                    row = await conn.fetchrow(
                        """
                        INSERT INTO kb_chunks (collection_id, content, metadata, source)
                        VALUES ($1, $2, $3::jsonb, $4)
                        RETURNING id
                        """,
                        collection_id,
                        item["content"],
                        json.dumps(item.get("metadata", {})),
                        item.get("source", ""),
                    )
                chunk_id = int(row["id"])
                ids.append(chunk_id)

                if item.get("build_graph", True):
                    from herness.rag.graph.extractor import (
                        extract_entities_from_text,
                        extract_relations_from_text,
                    )

                    for entity in extract_entities_from_text(item["content"], chunk_id):
                        await self._upsert_entity(conn, collection_id, entity, chunk_id)
                    for edge in extract_relations_from_text(item["content"], chunk_id):
                        from herness.rag.graph.extractor import GraphEntity

                        await self._upsert_entity(
                            conn,
                            collection_id,
                            GraphEntity(name=edge.source, entity_type="named"),
                            chunk_id,
                        )
                        await self._upsert_entity(
                            conn,
                            collection_id,
                            GraphEntity(name=edge.target, entity_type="named"),
                            chunk_id,
                        )
                        await self._insert_edge(conn, collection_id, edge, chunk_id)
        return ids

    async def insert_graph(
        self,
        collection_id: str,
        entities: list[dict[str, Any]],
        edges: list[dict[str, Any]],
    ) -> None:
        async with self._pool.acquire() as conn:
            for entity in entities:
                for chunk_id in entity.get("chunk_ids", []):
                    from herness.rag.graph.extractor import GraphEntity

                    await self._upsert_entity(
                        conn,
                        collection_id,
                        GraphEntity(
                            name=entity["name"],
                            entity_type=entity.get("entity_type", "concept"),
                            chunk_ids=[chunk_id],
                        ),
                        chunk_id,
                    )
            for edge in edges:
                from herness.rag.graph.extractor import GraphEdge

                await self._insert_edge(
                    conn,
                    collection_id,
                    GraphEdge(
                        source=edge["source"],
                        target=edge["target"],
                        relation=edge.get("relation", "related_to"),
                        chunk_id=edge.get("chunk_id"),
                    ),
                    edge.get("chunk_id"),
                )

    async def upsert_community_summary(
        self,
        collection_id: str,
        community_id: str,
        summary: str,
        *,
        entity_names: list[str] | None = None,
    ) -> None:
        await self._pool.execute(
            """
            INSERT INTO kb_communities (collection_id, community_id, summary, entity_names)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (collection_id, community_id)
            DO UPDATE SET summary = EXCLUDED.summary, entity_names = EXCLUDED.entity_names
            """,
            collection_id,
            community_id,
            summary,
            entity_names or [],
        )

    async def search_communities(
        self,
        collection_id: str,
        query: str,
        *,
        limit: int = 3,
    ) -> list[dict[str, Any]]:
        rows = await self._pool.fetch(
            """
            SELECT community_id, summary, entity_names,
                   ts_rank(summary_tsv, plainto_tsquery('simple', $2)) AS score
            FROM kb_communities
            WHERE collection_id = $1
              AND summary_tsv @@ plainto_tsquery('simple', $2)
            ORDER BY score DESC
            LIMIT $3
            """,
            collection_id,
            query,
            limit,
        )
        return [dict(row) for row in rows]

    async def _upsert_entity(
        self,
        conn: Any,
        collection_id: str,
        entity: Any,
        chunk_id: int,
    ) -> None:
        await conn.execute(
            """
            INSERT INTO kb_entities (collection_id, name, entity_type, chunk_ids)
            VALUES ($1, $2, $3, ARRAY[$4]::bigint[])
            ON CONFLICT (collection_id, name) DO UPDATE
            SET chunk_ids = (
                SELECT ARRAY(
                    SELECT DISTINCT unnest(kb_entities.chunk_ids || EXCLUDED.chunk_ids)
                )
            )
            """,
            collection_id,
            entity.name,
            entity.entity_type,
            chunk_id,
        )

    async def _insert_edge(
        self,
        conn: Any,
        collection_id: str,
        edge: Any,
        chunk_id: int | None,
    ) -> None:
        await conn.execute(
            """
            INSERT INTO kb_edges (collection_id, source_name, target_name, relation, chunk_id)
            VALUES ($1, $2, $3, $4, $5)
            ON CONFLICT (collection_id, source_name, target_name, relation) DO NOTHING
            """,
            collection_id,
            edge.source,
            edge.target,
            edge.relation,
            chunk_id,
        )


def _row_to_chunk(row: Any) -> dict[str, Any]:
    metadata = row["metadata"]
    if isinstance(metadata, str):
        metadata = json.loads(metadata)
    chunk = {
        "id": int(row["id"]),
        "collection_id": row["collection_id"],
        "content": row["content"],
        "metadata": metadata or {},
        "source": row.get("source") or "",
    }
    if "fts_rank" in row.keys():
        chunk["fts_rank"] = float(row["fts_rank"] or 0.0)
    if "vector_similarity" in row.keys():
        chunk["vector_similarity"] = float(row["vector_similarity"] or 0.0)
    return chunk


_BASE_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS kb_collections (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    persona TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS kb_chunks (
    id BIGSERIAL PRIMARY KEY,
    collection_id TEXT NOT NULL REFERENCES kb_collections(id) ON DELETE CASCADE,
    content TEXT NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    source TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_kb_chunks_collection ON kb_chunks (collection_id);

ALTER TABLE kb_chunks
    ADD COLUMN IF NOT EXISTS content_tsv tsvector
    GENERATED ALWAYS AS (to_tsvector('simple', coalesce(content, ''))) STORED;

CREATE INDEX IF NOT EXISTS idx_kb_chunks_content_tsv ON kb_chunks USING GIN (content_tsv);

CREATE TABLE IF NOT EXISTS kb_entities (
    id BIGSERIAL PRIMARY KEY,
    collection_id TEXT NOT NULL REFERENCES kb_collections(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    entity_type TEXT NOT NULL DEFAULT 'concept',
    chunk_ids BIGINT[] NOT NULL DEFAULT '{}',
    UNIQUE (collection_id, name)
);

CREATE INDEX IF NOT EXISTS idx_kb_entities_collection ON kb_entities (collection_id);

CREATE TABLE IF NOT EXISTS kb_edges (
    id BIGSERIAL PRIMARY KEY,
    collection_id TEXT NOT NULL REFERENCES kb_collections(id) ON DELETE CASCADE,
    source_name TEXT NOT NULL,
    target_name TEXT NOT NULL,
    relation TEXT NOT NULL DEFAULT 'related_to',
    chunk_id BIGINT REFERENCES kb_chunks(id) ON DELETE SET NULL,
    UNIQUE (collection_id, source_name, target_name, relation)
);

CREATE INDEX IF NOT EXISTS idx_kb_edges_collection ON kb_edges (collection_id);

CREATE TABLE IF NOT EXISTS kb_communities (
    id BIGSERIAL PRIMARY KEY,
    collection_id TEXT NOT NULL REFERENCES kb_collections(id) ON DELETE CASCADE,
    community_id TEXT NOT NULL,
    summary TEXT NOT NULL,
    entity_names TEXT[] NOT NULL DEFAULT '{}',
    UNIQUE (collection_id, community_id)
);

ALTER TABLE kb_communities
    ADD COLUMN IF NOT EXISTS summary_tsv tsvector
    GENERATED ALWAYS AS (to_tsvector('simple', coalesce(summary, ''))) STORED;

CREATE INDEX IF NOT EXISTS idx_kb_communities_summary_tsv ON kb_communities USING GIN (summary_tsv);
"""
