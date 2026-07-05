"""信念库查询逻辑 — InMemory / Postgres 共用。"""

from typing import Any


def match_beliefs(user_beliefs: list[dict[str, Any]], claims: list[str]) -> list[dict[str, Any]]:
    """将声明与信念库条目做关键词匹配。"""
    results: list[dict[str, Any]] = []
    for claim in claims:
        matched = [
            b for b in user_beliefs if claim.lower() in b.get("fact", "").lower()
        ]
        if matched:
            results.append({"claim": claim, "status": "supported", "matches": matched})
        else:
            results.append({"claim": claim, "status": "unknown", "matches": []})
    return results
