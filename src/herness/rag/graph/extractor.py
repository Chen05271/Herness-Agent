"""GraphRAG — 实体/关系抽取与子图检索。"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from herness.middleware.beliefs import extract_search_terms

_RELATION_PATTERNS = (
    re.compile(r"(.+?)(?:是|为|属于|包含|关联|连接|使用|依赖|产自|来自|位于|销往|包括)(.+?)(?:[。，,；;]|$)"),
    re.compile(r"(.+?)\s+(?:is|are|has|uses|depends on|belongs to)\s+(.+?)(?:[.,;]|$)", re.I),
)

# GraphRAG / Markdown 风格：[实体A] --关系--> [实体B]
_MARKDOWN_EDGE_PATTERN = re.compile(
    r"\[(.+?)\]\s*--(.+?)-->\s*\[(.+?)\]",
)
_MARKDOWN_ARROW_EDGE_PATTERN = re.compile(
    r"\[(.+?)\]\s*-->\s*\[(.+?)\]",
)


def _add_entity(
    entities: dict[str, GraphEntity],
    name: str,
    entity_type: str,
    chunk_id: int | None,
) -> None:
    cleaned = name.strip()
    if len(cleaned) < 2:
        return
    key = cleaned.lower()
    if key not in entities:
        entities[key] = GraphEntity(name=cleaned, entity_type=entity_type)
    if chunk_id is not None and chunk_id not in entities[key].chunk_ids:
        entities[key].chunk_ids.append(chunk_id)


def _append_edge(
    edges: list[GraphEdge],
    *,
    source: str,
    target: str,
    relation: str,
    chunk_id: int | None,
) -> None:
    src = source.strip()
    tgt = target.strip()
    rel = relation.strip() or "related_to"
    if len(src) < 2 or len(tgt) < 2:
        return
    for edge in edges:
        if (
            edge.source.lower() == src.lower()
            and edge.target.lower() == tgt.lower()
            and edge.relation == rel
        ):
            return
    edges.append(
        GraphEdge(
            source=src,
            target=tgt,
            relation=rel,
            chunk_id=chunk_id,
        )
    )


@dataclass
class GraphEntity:
    name: str
    entity_type: str = "concept"
    chunk_ids: list[int] = field(default_factory=list)


@dataclass
class GraphEdge:
    source: str
    target: str
    relation: str
    chunk_id: int | None = None


def extract_entities_from_text(text: str, chunk_id: int | None = None) -> list[GraphEntity]:
    """启发式实体抽取（无需 LLM，适合测试与轻量建图）。"""
    entities: dict[str, GraphEntity] = {}

    for term in extract_search_terms(text):
        if len(term) >= 2:
            key = term.lower()
            if key not in entities:
                entities[key] = GraphEntity(name=term, entity_type="term")
            if chunk_id is not None and chunk_id not in entities[key].chunk_ids:
                entities[key].chunk_ids.append(chunk_id)

    for match in re.finditer(r"[「『\"](.+?)[」』\"]", text):
        _add_entity(entities, match.group(1), "named", chunk_id)

    for match in re.finditer(r"\[(.+?)\]", text):
        _add_entity(entities, match.group(1), "named", chunk_id)

    return list(entities.values())


def extract_relations_from_text(text: str, chunk_id: int | None = None) -> list[GraphEdge]:
    """启发式关系抽取。"""
    edges: list[GraphEdge] = []

    for match in _MARKDOWN_EDGE_PATTERN.finditer(text):
        _append_edge(
            edges,
            source=match.group(1),
            target=match.group(3),
            relation=match.group(2),
            chunk_id=chunk_id,
        )

    for match in _MARKDOWN_ARROW_EDGE_PATTERN.finditer(text):
        _append_edge(
            edges,
            source=match.group(1),
            target=match.group(2),
            relation="related_to",
            chunk_id=chunk_id,
        )

    for pattern in _RELATION_PATTERNS:
        for match in pattern.finditer(text):
            source = match.group(1).strip()
            target = match.group(2).strip()
            if any(token in source or token in target for token in ("-->", "--", "[", "]")):
                continue
            _append_edge(
                edges,
                source=source,
                target=target,
                relation="related_to",
                chunk_id=chunk_id,
            )
    return edges


def link_query_entities(
    query: str,
    entity_names: list[str],
) -> list[str]:
    """将 query 词项与已有实体名做模糊链接。"""
    query_terms = {t.lower() for t in extract_search_terms(query)}
    query_terms.update(t.lower() for t in extract_identifiers_from_query(query))
    linked: list[str] = []
    for name in entity_names:
        name_lower = name.lower()
        if name_lower in query_terms:
            linked.append(name)
            continue
        if any(term in name_lower or name_lower in term for term in query_terms):
            linked.append(name)
    return linked


def extract_identifiers_from_query(query: str) -> list[str]:
    from herness.rag.grep.retrieval import extract_identifiers

    return extract_identifiers(query)


def expand_subgraph_chunk_ids(
    seed_entity_names: list[str],
    entities: list[dict[str, Any]],
    edges: list[dict[str, Any]],
    *,
    max_hops: int = 2,
) -> dict[int, float]:
    """从种子实体做 BFS 子图扩展，返回 chunk_id → graph_score。"""
    name_to_entity = {e["name"].lower(): e for e in entities}
    adjacency: dict[str, set[str]] = {}
    entity_chunks: dict[str, set[int]] = {}

    for entity in entities:
        key = entity["name"].lower()
        entity_chunks[key] = set(entity.get("chunk_ids") or [])

    for edge in edges:
        src = edge["source"].lower()
        tgt = edge["target"].lower()
        adjacency.setdefault(src, set()).add(tgt)
        adjacency.setdefault(tgt, set()).add(src)

    visited: set[str] = set()
    chunk_scores: dict[int, float] = {}
    queue: list[tuple[str, int]] = []

    for seed in seed_entity_names:
        key = seed.lower()
        if key in name_to_entity:
            queue.append((key, 0))

    while queue:
        name_key, hop = queue.pop(0)
        if name_key in visited:
            continue
        visited.add(name_key)

        score = 1.0 / (1 + hop)
        for chunk_id in entity_chunks.get(name_key, set()):
            chunk_scores[chunk_id] = max(chunk_scores.get(chunk_id, 0.0), score)

        if hop >= max_hops:
            continue
        for neighbor in adjacency.get(name_key, set()):
            if neighbor not in visited:
                queue.append((neighbor, hop + 1))

    return chunk_scores
