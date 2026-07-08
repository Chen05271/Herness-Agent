"""检索结果融合 — RRF（Reciprocal Rank Fusion）。"""

from __future__ import annotations

from typing import Any


def reciprocal_rank_fusion(
    ranked_lists: list[list[int]],
    *,
    k: int = 60,
) -> dict[int, float]:
    """对多个排序列表做 RRF 合并，返回 chunk_id → score。"""
    scores: dict[int, float] = {}
    for ranked in ranked_lists:
        for rank, chunk_id in enumerate(ranked, start=1):
            scores[chunk_id] = scores.get(chunk_id, 0.0) + 1.0 / (k + rank)
    return scores


def merge_candidate_metadata(
    base: dict[str, Any],
    incoming: dict[str, Any],
) -> dict[str, Any]:
    """合并同一 chunk 的多通道元数据。"""
    merged = dict(base)
    for key, value in incoming.items():
        if key not in merged:
            merged[key] = value
        elif isinstance(merged[key], (int, float)) and isinstance(value, (int, float)):
            merged[key] = max(float(merged[key]), float(value))
        elif key == "channels":
            channels = set(merged.get("channels", []))
            channels.update(value if isinstance(value, list) else [value])
            merged["channels"] = sorted(channels)
    return merged
