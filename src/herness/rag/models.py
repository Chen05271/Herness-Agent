"""RAG 检索数据模型。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class RagChunk:
    """知识库文档块。"""

    id: int
    collection_id: str
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)
    source: str = ""


@dataclass
class RagHit:
    """单条检索命中。"""

    chunk_id: int
    content: str
    score: float
    source: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    retrieval_channel: str = ""
    fts_rank: float = 0.0
    vector_similarity: float = 0.0
    graph_score: float = 0.0
    rerank_score: float = 0.0


@dataclass
class RagSearchResult:
    """完整检索结果。"""

    query: str
    collection_id: str
    hits: list[RagHit]
    coarse_count: int = 0
    fine_count: int = 0
