"""内存知识库 — 测试与无 Postgres 场景。"""

from __future__ import annotations

from typing import Any

from herness.middleware.beliefs import extract_search_terms
from herness.rag.grep.retrieval import build_grep_patterns, grep_match_score
from herness.rag.graph.extractor import (
    extract_entities_from_text,
    extract_relations_from_text,
)


class InMemoryKnowledgeStore:
    """基于 dict 的知识库实现。"""

    def __init__(self) -> None:
        self._collections: dict[str, dict[str, Any]] = {}
        self._chunks: dict[str, list[dict[str, Any]]] = {}
        self._entities: dict[str, list[dict[str, Any]]] = {}
        self._edges: dict[str, list[dict[str, Any]]] = {}
        self._communities: dict[str, list[dict[str, Any]]] = {}
        self._next_chunk_id = 1

    async def fts_search(
        self,
        collection_id: str,
        query: str,
        *,
        limit: int,
        min_rank: float,
    ) -> list[dict[str, Any]]:
        terms = extract_search_terms(query)
        if not terms:
            return []
        hits: list[dict[str, Any]] = []
        for chunk in self._chunks.get(collection_id, []):
            content_lower = chunk["content"].lower()
            overlap = sum(1 for t in terms if t.lower() in content_lower)
            if overlap == 0:
                continue
            rank = overlap / len(terms)
            if rank >= min_rank:
                hits.append({**chunk, "fts_rank": rank})
        hits.sort(key=lambda h: h["fts_rank"], reverse=True)
        return hits[:limit]

    async def grep_search(
        self,
        collection_id: str,
        query: str,
        *,
        limit: int,
    ) -> list[dict[str, Any]]:
        patterns = [p.strip("%").lower() for p in build_grep_patterns(query)]
        if not patterns:
            return await self.fts_search(collection_id, query, limit=limit, min_rank=0.01)

        hits: list[dict[str, Any]] = []
        for chunk in self._chunks.get(collection_id, []):
            content_lower = chunk["content"].lower()
            if any(p in content_lower for p in patterns):
                score = grep_match_score(query, chunk["content"])
                hits.append({**chunk, "fts_rank": score, "grep_score": score})
        hits.sort(key=lambda h: h.get("grep_score", 0.0), reverse=True)
        return hits[:limit]

    async def vector_search(
        self,
        collection_id: str,
        query_vector: list[float],
        *,
        limit: int,
        min_similarity: float,
    ) -> list[dict[str, Any]]:
        hits: list[dict[str, Any]] = []
        for chunk in self._chunks.get(collection_id, []):
            embedding = chunk.get("embedding")
            if not embedding:
                continue
            sim = _cosine_similarity(query_vector, embedding)
            if sim >= min_similarity:
                hits.append({**chunk, "vector_similarity": sim})
        hits.sort(key=lambda h: h["vector_similarity"], reverse=True)
        return hits[:limit]

    async def get_chunks_by_ids(
        self,
        collection_id: str,
        chunk_ids: list[int],
    ) -> list[dict[str, Any]]:
        id_set = set(chunk_ids)
        return [c for c in self._chunks.get(collection_id, []) if c["id"] in id_set]

    async def list_entities(self, collection_id: str) -> list[dict[str, Any]]:
        return list(self._entities.get(collection_id, []))

    async def list_edges(self, collection_id: str) -> list[dict[str, Any]]:
        return list(self._edges.get(collection_id, []))

    async def list_communities(self, collection_id: str) -> list[dict[str, Any]]:
        return list(self._communities.get(collection_id, []))

    async def upsert_collection(
        self,
        collection_id: str,
        name: str,
        *,
        persona: str | None = None,
    ) -> None:
        self._collections[collection_id] = {
            "id": collection_id,
            "name": name,
            "persona": persona,
        }
        self._chunks.setdefault(collection_id, [])
        self._entities.setdefault(collection_id, [])
        self._edges.setdefault(collection_id, [])
        self._communities.setdefault(collection_id, [])

    async def insert_chunks(
        self,
        collection_id: str,
        chunks: list[dict[str, Any]],
    ) -> list[int]:
        self._chunks.setdefault(collection_id, [])
        ids: list[int] = []
        for item in chunks:
            chunk_id = self._next_chunk_id
            self._next_chunk_id += 1
            record = {
                "id": chunk_id,
                "collection_id": collection_id,
                "content": item["content"],
                "metadata": item.get("metadata", {}),
                "source": item.get("source", ""),
                "embedding": item.get("embedding"),
            }
            self._chunks[collection_id].append(record)
            ids.append(chunk_id)

            if item.get("build_graph", True):
                for entity in extract_entities_from_text(item["content"], chunk_id):
                    self._upsert_entity(collection_id, entity.name, entity.entity_type, chunk_id)
                for edge in extract_relations_from_text(item["content"], chunk_id):
                    self._upsert_entity(collection_id, edge.source, "named", chunk_id)
                    self._upsert_entity(collection_id, edge.target, "named", chunk_id)
                    self._upsert_edge(
                        collection_id, edge.source, edge.target, edge.relation, chunk_id
                    )
        return ids

    async def insert_graph(
        self,
        collection_id: str,
        entities: list[dict[str, Any]],
        edges: list[dict[str, Any]],
    ) -> None:
        for entity in entities:
            for chunk_id in entity.get("chunk_ids", []):
                self._upsert_entity(
                    collection_id,
                    entity["name"],
                    entity.get("entity_type", "concept"),
                    chunk_id,
                )
        for edge in edges:
            self._upsert_edge(
                collection_id,
                edge["source"],
                edge["target"],
                edge.get("relation", "related_to"),
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
        self._communities.setdefault(collection_id, [])
        for item in self._communities[collection_id]:
            if item["community_id"] == community_id:
                item["summary"] = summary
                item["entity_names"] = entity_names or []
                return
        self._communities[collection_id].append(
            {
                "community_id": community_id,
                "summary": summary,
                "entity_names": entity_names or [],
            }
        )

    async def search_communities(
        self,
        collection_id: str,
        query: str,
        *,
        limit: int = 3,
    ) -> list[dict[str, Any]]:
        terms = {t.lower() for t in extract_search_terms(query)}
        hits: list[dict[str, Any]] = []
        for item in self._communities.get(collection_id, []):
            text = item["summary"].lower()
            score = sum(1 for t in terms if t in text) / max(len(terms), 1)
            if score > 0:
                hits.append({**item, "score": score})
        hits.sort(key=lambda h: h["score"], reverse=True)
        return hits[:limit]

    def _upsert_entity(
        self,
        collection_id: str,
        name: str,
        entity_type: str,
        chunk_id: int,
    ) -> None:
        self._entities.setdefault(collection_id, [])
        key = name.lower()
        for entity in self._entities[collection_id]:
            if entity["name"].lower() == key:
                if chunk_id not in entity["chunk_ids"]:
                    entity["chunk_ids"].append(chunk_id)
                return
        self._entities[collection_id].append(
            {"name": name, "entity_type": entity_type, "chunk_ids": [chunk_id]}
        )

    def _upsert_edge(
        self,
        collection_id: str,
        source: str,
        target: str,
        relation: str,
        chunk_id: int | None,
    ) -> None:
        self._edges.setdefault(collection_id, [])
        for edge in self._edges[collection_id]:
            if (
                edge["source"].lower() == source.lower()
                and edge["target"].lower() == target.lower()
                and edge["relation"] == relation
            ):
                return
        self._edges[collection_id].append(
            {
                "source": source,
                "target": target,
                "relation": relation,
                "chunk_id": chunk_id,
            }
        )


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    if len(a) != len(b) or not a:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(x * x for x in b) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)
