"""知识库存储协议。"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class KnowledgeStore(Protocol):
    """RAG 知识库读写接口。"""

    async def fts_search(
        self,
        collection_id: str,
        query: str,
        *,
        limit: int,
        min_rank: float,
    ) -> list[dict[str, Any]]: ...

    async def grep_search(
        self,
        collection_id: str,
        query: str,
        *,
        limit: int,
    ) -> list[dict[str, Any]]: ...

    async def vector_search(
        self,
        collection_id: str,
        query_vector: list[float],
        *,
        limit: int,
        min_similarity: float,
    ) -> list[dict[str, Any]]: ...

    async def get_chunks_by_ids(
        self,
        collection_id: str,
        chunk_ids: list[int],
    ) -> list[dict[str, Any]]: ...

    async def list_entities(self, collection_id: str) -> list[dict[str, Any]]: ...

    async def list_edges(self, collection_id: str) -> list[dict[str, Any]]: ...

    async def list_communities(self, collection_id: str) -> list[dict[str, Any]]: ...

    async def upsert_collection(
        self,
        collection_id: str,
        name: str,
        *,
        persona: str | None = None,
    ) -> None: ...

    async def insert_chunks(
        self,
        collection_id: str,
        chunks: list[dict[str, Any]],
    ) -> list[int]: ...

    async def insert_graph(
        self,
        collection_id: str,
        entities: list[dict[str, Any]],
        edges: list[dict[str, Any]],
    ) -> None: ...

    async def upsert_community_summary(
        self,
        collection_id: str,
        community_id: str,
        summary: str,
        *,
        entity_names: list[str] | None = None,
    ) -> None: ...

    async def search_communities(
        self,
        collection_id: str,
        query: str,
        *,
        limit: int = 3,
    ) -> list[dict[str, Any]]: ...
