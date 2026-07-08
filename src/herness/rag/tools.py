"""RAG 工具输出格式化 — 供 Worker 工具使用。"""

from __future__ import annotations

from herness.rag.models import RagSearchResult


def format_rag_context(result: RagSearchResult) -> str:
    """将检索结果格式化为 Worker 可读文本。"""
    if not result.hits:
        return f"知识库「{result.collection_id}」未找到与「{result.query}」相关的内容。"

    lines = [
        f"知识库「{result.collection_id}」检索结果（粗召回 {result.coarse_count} → 精排 {len(result.hits)}）：",
        "",
    ]
    for idx, hit in enumerate(result.hits, start=1):
        lines.append(f"--- 片段 {idx}（score={hit.score:.3f}，来源={hit.source or '未知'}）---")
        lines.append(hit.content.strip())
        if hit.retrieval_channel:
            lines.append(f"[通道: {hit.retrieval_channel}]")
        lines.append("")
    return "\n".join(lines).strip()
