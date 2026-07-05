"""信念库查询逻辑 — 关键词匹配 / Hereness 深度检索 / 矛盾检测。"""

from __future__ import annotations

import re
from typing import Any, Literal

FactStatus = Literal["supported", "contradicted", "unknown"]
BeliefStatus = Literal["active", "superseded"]

_NEGATION_MARKERS = (
    "不",
    "没",
    "非",
    "无",
    "未",
    "not ",
    "n't",
    "never ",
    "no ",
)

_MATCH_SCORE_THRESHOLD = 0.25


def extract_search_terms(text: str) -> list[str]:
    """从混合中英文文本提取可检索词项。"""
    terms: list[str] = []
    for match in re.finditer(r"[a-zA-Z][a-zA-Z0-9]{1,}", text):
        terms.append(match.group().lower())
    for match in re.finditer(r"[\u4e00-\u9fff]{2,}", text):
        terms.append(match.group())

    seen: set[str] = set()
    unique: list[str] = []
    for term in terms:
        if term not in seen:
            seen.add(term)
            unique.append(term)
    return unique


def has_negation(text: str) -> bool:
    lower = text.lower()
    return any(marker in lower for marker in _NEGATION_MARKERS)


def is_contradiction(claim: str, fact: str) -> bool:
    """启发式矛盾检测：共享主题且极性相反。"""
    claim_terms = set(extract_search_terms(claim))
    fact_terms = set(extract_search_terms(fact))
    if not claim_terms or not fact_terms:
        return False
    if len(claim_terms & fact_terms) < 1:
        return False
    return has_negation(claim) != has_negation(fact)


def score_belief_match(claim: str, fact: str) -> float:
    """基于词项重叠与包含关系计算匹配分（0–1）。"""
    claim_lower = claim.lower()
    fact_lower = fact.lower()
    if claim_lower in fact_lower or fact_lower in claim_lower:
        return 1.0

    claim_terms = set(extract_search_terms(claim))
    fact_terms = set(extract_search_terms(fact))
    if not claim_terms or not fact_terms:
        return 0.0

    direct_overlap = len(claim_terms & fact_terms)
    jaccard = direct_overlap / len(claim_terms | fact_terms) if direct_overlap > 0 else 0.0

    substring_hits = sum(1 for term in claim_terms if term.lower() in fact_lower)
    substring_score = substring_hits / len(claim_terms)
    return max(jaccard, substring_score)


def _active_beliefs(matches: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [b for b in matches if b.get("status", "active") == "active"]


def classify_claim_status(claim: str, matches: list[dict[str, Any]]) -> FactStatus:
    """根据匹配信念判定声明状态；存在冲突时按置信度消歧。"""
    active = _active_beliefs(matches)
    if not active:
        return "unknown"

    supporting: list[dict[str, Any]] = []
    contradicting: list[dict[str, Any]] = []
    for belief in active:
        if is_contradiction(claim, belief.get("fact", "")):
            contradicting.append(belief)
        else:
            supporting.append(belief)

    if not contradicting:
        return "supported"
    if not supporting:
        return "contradicted"

    best_support = max(supporting, key=lambda b: float(b.get("confidence", 0.0)))
    best_contra = max(contradicting, key=lambda b: float(b.get("confidence", 0.0)))
    support_conf = float(best_support.get("confidence", 0.0))
    contra_conf = float(best_contra.get("confidence", 0.0))

    if support_conf > contra_conf:
        return "supported"
    if contra_conf > support_conf:
        return "contradicted"
    return "contradicted"


def resolve_belief_write_conflict(
    new_fact: str,
    new_confidence: float,
    existing_beliefs: list[dict[str, Any]],
    *,
    decay_factor: float = 0.5,
    superseded_threshold: float = 0.3,
) -> tuple[float, BeliefStatus, list[dict[str, Any]]]:
    """写入新信念前处理冲突：返回 (调整后置信度, 新信念状态, 既有信念更新列表)。"""
    adjusted = new_confidence
    new_status: BeliefStatus = "active"
    updates: list[dict[str, Any]] = []

    for belief in existing_beliefs:
        if belief.get("status", "active") != "active":
            continue
        if not is_contradiction(new_fact, belief.get("fact", "")):
            continue

        belief_id = belief.get("id")
        if belief_id is None:
            continue

        old_conf = float(belief.get("confidence", 1.0))
        if adjusted > old_conf:
            updates.append({"id": belief_id, "status": "superseded"})
        elif adjusted < old_conf:
            adjusted *= decay_factor
            if adjusted < superseded_threshold:
                new_status = "superseded"
        else:
            decayed = old_conf * decay_factor
            update: dict[str, Any] = {"id": belief_id, "confidence": decayed}
            if decayed < superseded_threshold:
                update["status"] = "superseded"
            updates.append(update)
            adjusted *= decay_factor
            if adjusted < superseded_threshold:
                new_status = "superseded"

    return adjusted, new_status, updates


def match_beliefs(
    user_beliefs: list[dict[str, Any]],
    claims: list[str],
    *,
    deep: bool = False,
) -> list[dict[str, Any]]:
    """将声明与信念库条目匹配；deep=True 时启用 Hereness 评分与矛盾检测。"""
    results: list[dict[str, Any]] = []
    for claim in claims:
        if not deep:
            matched = [b for b in user_beliefs if claim.lower() in b.get("fact", "").lower()]
            status: FactStatus = "supported" if matched else "unknown"
            results.append({"claim": claim, "status": status, "matches": matched})
            continue

        scored: list[tuple[float, dict[str, Any]]] = []
        for belief in user_beliefs:
            score = score_belief_match(claim, belief.get("fact", ""))
            if score >= _MATCH_SCORE_THRESHOLD:
                scored.append((score, belief))
        scored.sort(key=lambda item: item[0], reverse=True)
        matched = [belief for _, belief in scored]
        status = classify_claim_status(claim, matched)
        results.append({"claim": claim, "status": status, "matches": matched})

    return results


def extract_claims_from_text(text: str, *, max_claims: int = 5) -> list[str]:
    """从 Worker 输出中提取待核查声明（按句子切分）。"""
    chunks = re.split(r"[。！？\n；;]+", text)
    claims: list[str] = []
    for chunk in chunks:
        cleaned = chunk.strip()
        if len(cleaned) >= 6:
            claims.append(cleaned)
        if len(claims) >= max_claims:
            break
    return claims
