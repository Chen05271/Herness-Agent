"""RAG 检索管线 — 粗检索 → 细检索 → Re-rank。"""

from __future__ import annotations

import logging
from typing import Any

from herness.config import Settings
from herness.middleware.embeddings import EmbeddingClient
from herness.rag.fusion import merge_candidate_metadata, reciprocal_rank_fusion
from herness.rag.graph.extractor import expand_subgraph_chunk_ids, link_query_entities
from herness.rag.models import RagHit, RagSearchResult
from herness.rag.rerank import CrossEncoderReranker, HybridReranker
from herness.rag.store.protocol import KnowledgeStore

logger = logging.getLogger(__name__)


class RagPipeline:
    """三阶段 RAG 检索：粗检索（GrepRAG + 向量 + GraphRAG）→ 细检索 → Re-rank。"""

    def __init__(
        self,
        store: KnowledgeStore,
        settings: Settings,
        *,
        embedding_client: EmbeddingClient | None = None,
    ) -> None:
        self._store = store
        self._settings = settings
        self._embedding_client = embedding_client
        self._reranker = self._build_reranker(settings)

    def _build_reranker(self, settings: Settings) -> HybridReranker:
        cross_encoder = None
        if settings.rag_rerank_enabled and settings.rag_rerank_model:
            base_url = settings.rag_rerank_base_url or settings.llm_base_url
            api_key = settings.rag_rerank_api_key or settings.llm_api_key
            cross_encoder = CrossEncoderReranker(
                base_url=base_url,
                api_key=api_key,
                model=settings.rag_rerank_model,
            )
        return HybridReranker(cross_encoder=cross_encoder)

    async def search(
        self,
        query: str,
        *,
        collection_id: str = "default",
    ) -> RagSearchResult:
        coarse = await self._coarse_retrieve(query, collection_id)
        fine = await self._fine_retrieve(query, collection_id, coarse)
        ranked = await self._reranker.rerank_candidates(query, fine)
        final = ranked[: self._settings.rag_final_top_k]

        hits = [
            RagHit(
                chunk_id=int(item["id"]),
                content=item["content"],
                score=float(item.get("rerank_score", 0.0)),
                source=item.get("source", ""),
                metadata=item.get("metadata", {}),
                retrieval_channel=",".join(item.get("channels", [])),
                fts_rank=float(item.get("fts_rank", 0.0)),
                vector_similarity=float(item.get("vector_similarity", 0.0)),
                graph_score=float(item.get("graph_score", 0.0)),
                rerank_score=float(item.get("rerank_score", 0.0)),
            )
            for item in final
        ]
        return RagSearchResult(
            query=query,
            collection_id=collection_id,
            hits=hits,
            coarse_count=len(coarse),
            fine_count=len(fine),
        )

    async def _coarse_retrieve(
        self,
        query: str,
        collection_id: str,
    ) -> list[dict[str, Any]]:
        settings = self._settings
        ranked_lists: list[list[int]] = []
        candidates: dict[int, dict[str, Any]] = {}

        def _absorb(hits: list[dict[str, Any]], channel: str) -> None:
            ids: list[int] = []
            for hit in hits:
                chunk_id = int(hit["id"])
                ids.append(chunk_id)
                if chunk_id in candidates:
                    existing = candidates[chunk_id]
                    existing["channels"] = sorted(set(existing.get("channels", [])) | {channel})
                    candidates[chunk_id] = merge_candidate_metadata(existing, hit)
                else:
                    hit["channels"] = [channel]
                    candidates[chunk_id] = hit
            if ids:
                ranked_lists.append(ids)

        if settings.rag_grep_enabled:
            grep_hits = await self._store.grep_search(
                collection_id,
                query,
                limit=settings.rag_coarse_top_k,
            )
            _absorb(grep_hits, "grep")

        fts_hits = await self._store.fts_search(
            collection_id,
            query,
            limit=settings.rag_coarse_top_k,
            min_rank=settings.rag_fts_min_rank,
        )
        _absorb(fts_hits, "fts")

        if (
            settings.rag_vector_enabled
            and self._embedding_client is not None
        ):
            try:
                query_vector = await self._embedding_client.embed_one(query)
                vector_hits = await self._store.vector_search(
                    collection_id,
                    query_vector,
                    limit=settings.rag_coarse_top_k,
                    min_similarity=settings.rag_vector_min_similarity,
                )
                _absorb(vector_hits, "vector")
            except Exception as exc:
                logger.warning("RAG 向量粗检索失败: %s", exc)

        if settings.rag_graph_enabled:
            graph_hits = await self._graph_coarse_search(query, collection_id)
            _absorb(graph_hits, "graph")

        if settings.rag_community_enabled:
            communities = await self._store.search_communities(
                collection_id, query, limit=2
            )
            for comm in communities:
                summary_hit = {
                    "id": -1,
                    "content": comm["summary"],
                    "source": f"community:{comm['community_id']}",
                    "metadata": {"community_id": comm["community_id"]},
                    "fts_rank": float(comm.get("score", 0.5)),
                }
                # 社区摘要作为虚拟候选（id=-1 不参与 RRF，仅补充上下文）
                candidates[-1] = {**summary_hit, "channels": ["community"]}

        rrf_scores = reciprocal_rank_fusion(ranked_lists)
        for chunk_id, score in rrf_scores.items():
            if chunk_id in candidates:
                candidates[chunk_id]["rrf_score"] = score

        coarse = sorted(
            [c for cid, c in candidates.items() if cid >= 0],
            key=lambda c: c.get("rrf_score", 0.0),
            reverse=True,
        )
        return coarse[: settings.rag_coarse_top_k]

    async def _graph_coarse_search(
        self,
        query: str,
        collection_id: str,
    ) -> list[dict[str, Any]]:
        entities = await self._store.list_entities(collection_id)
        edges = await self._store.list_edges(collection_id)
        if not entities:
            return []

        entity_names = [e["name"] for e in entities]
        linked = link_query_entities(query, entity_names)
        if not linked:
            return []

        chunk_scores = expand_subgraph_chunk_ids(linked, entities, edges, max_hops=2)
        if not chunk_scores:
            return []

        top_ids = sorted(chunk_scores, key=chunk_scores.get, reverse=True)[
            : self._settings.rag_coarse_top_k
        ]
        chunks = await self._store.get_chunks_by_ids(collection_id, top_ids)
        for chunk in chunks:
            chunk["graph_score"] = chunk_scores.get(int(chunk["id"]), 0.0)
            chunk["fts_rank"] = chunk.get("fts_rank", chunk["graph_score"])
        return chunks

    async def _fine_retrieve(
        self,
        query: str,
        collection_id: str,
        coarse: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """细检索 — 邻块扩展 + 结构去重。"""
        if not coarse:
            return []

        settings = self._settings
        top = coarse[: settings.rag_fine_top_k]
        seen_sources: set[str] = set()
        deduped: list[dict[str, Any]] = []

        for item in top:
            source_key = item.get("source") or str(item["id"])
            content_prefix = item["content"][:80]
            dedup_key = f"{source_key}:{content_prefix}"
            if dedup_key in seen_sources:
                continue
            seen_sources.add(dedup_key)
            deduped.append(item)

        if settings.rag_graph_enabled and len(deduped) < settings.rag_fine_top_k:
            extra = await self._graph_coarse_search(query, collection_id)
            existing_ids = {int(c["id"]) for c in deduped}
            for hit in extra:
                if int(hit["id"]) not in existing_ids:
                    deduped.append(hit)
                if len(deduped) >= settings.rag_fine_top_k:
                    break

        return deduped[: settings.rag_fine_top_k]
