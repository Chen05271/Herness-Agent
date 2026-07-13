"""文档入库 — 分块、嵌入、建图。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from herness.config import Settings
from herness.middleware.embeddings import EmbeddingClient
from herness.models.usage import UsageSource
from herness.rag.chunker import chunk_text
from herness.rag.store.protocol import KnowledgeStore


async def ingest_text(
    store: KnowledgeStore,
    *,
    collection_id: str,
    collection_name: str,
    text: str,
    source: str = "",
    metadata: dict[str, Any] | None = None,
    settings: Settings,
    embedding_client: EmbeddingClient | None = None,
    persona: str | None = None,
    build_graph: bool = True,
    user_id: str = "",
) -> list[int]:
    """将文本分块写入知识库，可选嵌入与建图。"""
    await store.upsert_collection(collection_id, collection_name, persona=persona)

    pieces = chunk_text(
        text,
        chunk_size=settings.rag_ingest_chunk_size,
        chunk_overlap=settings.rag_ingest_chunk_overlap,
    )
    if not pieces:
        return []

    embeddings: list[list[float] | None] = [None] * len(pieces)
    if settings.rag_vector_enabled and embedding_client is not None:
        embeddings = await embedding_client.embed(
            pieces,
            user_id=user_id,
            source=UsageSource.RAG,
        )

    payloads: list[dict[str, Any]] = []
    base_meta = dict(metadata or {})
    for idx, piece in enumerate(pieces):
        payloads.append(
            {
                "content": piece,
                "source": source or base_meta.get("source", ""),
                "metadata": {**base_meta, "chunk_index": idx},
                "embedding": embeddings[idx],
                "build_graph": build_graph,
            }
        )

    return await store.insert_chunks(collection_id, payloads)


async def ingest_file(
    store: KnowledgeStore,
    *,
    path: Path,
    collection_id: str,
    collection_name: str,
    settings: Settings,
    embedding_client: EmbeddingClient | None = None,
    persona: str | None = None,
) -> list[int]:
    """从文件路径读取并入库。"""
    text = path.read_text(encoding="utf-8", errors="replace")
    return await ingest_text(
        store,
        collection_id=collection_id,
        collection_name=collection_name,
        text=text,
        source=str(path),
        metadata={"filename": path.name},
        settings=settings,
        embedding_client=embedding_client,
        persona=persona,
    )


async def build_community_summaries(
    store: KnowledgeStore,
    *,
    collection_id: str,
    min_entities: int = 2,
) -> int:
    """为共享 chunk 的实体簇生成社区摘要（轻量 GraphRAG）。"""
    entities = await store.list_entities(collection_id)
    if not entities:
        return 0

    clusters: dict[str, set[str]] = {}
    for entity in entities:
        chunk_ids = tuple(sorted(entity.get("chunk_ids") or []))
        if len(chunk_ids) < min_entities:
            continue
        key = ",".join(str(c) for c in chunk_ids)
        clusters.setdefault(key, set()).add(entity["name"])

    count = 0
    for idx, names in enumerate(clusters.values()):
        if len(names) < min_entities:
            continue
        summary = f"相关概念：{'、'.join(sorted(names))}。"
        community_id = f"cluster-{idx}"
        await store.upsert_community_summary(
            collection_id,
            community_id,
            summary,
            entity_names=sorted(names),
        )
        count += 1
    return count
