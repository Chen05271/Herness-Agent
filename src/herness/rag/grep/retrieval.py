"""GrepRAG 式词面粗检索 — FTS + 词项 ILIKE + identifier 提取。"""

from __future__ import annotations

import re
from typing import Any

from herness.middleware.beliefs import extract_search_terms

_IDENTIFIER_RE = re.compile(r"[a-zA-Z_][a-zA-Z0-9_]{1,}")
_CAMEL_RE = re.compile(r"[A-Z][a-z]+(?:[A-Z][a-z]+)+")
_SKU_RE = re.compile(r"\b[A-Z0-9]{2,}-[A-Z0-9-]+\b")


def extract_identifiers(text: str) -> list[str]:
    """从 query / chunk 提取 identifier（GrepRAG 加权用）。"""
    found: list[str] = []
    for pattern in (_IDENTIFIER_RE, _CAMEL_RE, _SKU_RE):
        for match in pattern.finditer(text):
            token = match.group()
            if len(token) >= 2:
                found.append(token)
    for term in extract_search_terms(text):
        if len(term) >= 3 and term not in found:
            found.append(term)
    return found


def grep_match_score(query: str, content: str, *, fts_rank: float = 0.0) -> float:
    """GrepRAG 式 identifier 加权得分。"""
    query_ids = set(extract_identifiers(query))
    content_lower = content.lower()
    if not query_ids:
        return fts_rank

    hits = sum(1 for ident in query_ids if ident.lower() in content_lower)
    id_score = hits / len(query_ids)
    return max(fts_rank, id_score * 0.6 + fts_rank * 0.4)


def build_grep_patterns(query: str) -> list[str]:
    """从 query 生成 ILIKE 搜索词项。"""
    terms = extract_search_terms(query)
    patterns: list[str] = []
    for term in terms:
        if len(term) >= 2:
            patterns.append(f"%{term}%")
    for ident in extract_identifiers(query):
        patterns.append(f"%{ident}%")
    return patterns[:10]


def rank_grep_hits(
    query: str,
    hits: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """对粗检索候选做 GrepRAG identifier 加权排序。"""
    for hit in hits:
        fts = float(hit.get("fts_rank", 0.0))
        hit["grep_score"] = grep_match_score(query, hit.get("content", ""), fts_rank=fts)
    return sorted(hits, key=lambda h: h.get("grep_score", 0.0), reverse=True)
