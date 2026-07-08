"""Critic Hereness 后校验 — 将信念库结果对齐到 FactCheckItem。"""

from __future__ import annotations

import json

from herness.agents.tool_policy import normalize_tool_name
from herness.agents.tool_trace import is_tool_result_error
from herness.integrations.agri_commerce.factory import AGRI_COMMERCE_READ_TOOLS
from herness.middleware.beliefs import extract_claims_from_text
from herness.middleware.protocol import ReadOnlyMiddleware
from herness.models.critic import CriticOutput, FactCheckItem, ToolCheckItem
from herness.models.worker import WorkerOutput

_EXTERNAL_TOOLS = frozenset(
    {"http_request", "read_text_file", "run_python_code"} | AGRI_COMMERCE_READ_TOOLS
)


def _evidence_from_matches(matches: list[dict]) -> str:
    if not matches:
        return ""
    parts = [m.get("fact", "") for m in matches[:3]]
    return "；".join(p for p in parts if p)


def _merge_fact_checks(
    existing: list[FactCheckItem],
    belief_results: list[dict],
) -> list[FactCheckItem]:
    """用信念库查询结果覆盖/补充 fact_checks。"""
    by_claim = {item.claim: item for item in existing}
    merged: list[FactCheckItem] = []

    for result in belief_results:
        claim = result["claim"]
        status = result["status"]
        evidence = _evidence_from_matches(result.get("matches", []))
        prior = by_claim.get(claim)
        if prior and prior.evidence and not evidence:
            evidence = prior.evidence
        merged.append(FactCheckItem(claim=claim, status=status, evidence=evidence))

    seen = {item.claim for item in merged}
    for item in existing:
        if item.claim not in seen:
            merged.append(item)

    return merged


def _build_contradiction_feedback(fact_checks: list[FactCheckItem]) -> str:
    lines = ["以下事实与 Hereness 信念库矛盾，请修正后重试："]
    for item in fact_checks:
        if item.status == "contradicted":
            detail = f"（证据：{item.evidence}）" if item.evidence else ""
            lines.append(f"- {item.claim}{detail}")
    return "\n".join(lines)


def collect_claims_for_verification(
    output: CriticOutput,
    worker_output: WorkerOutput,
) -> list[str]:
    """合并 LLM fact_checks 与 Worker 正文提取的声明，避免 LLM 漏检。"""
    claims: list[str] = []
    seen: set[str] = set()

    def _add(claim: str) -> None:
        cleaned = claim.strip()
        if cleaned and cleaned not in seen:
            seen.add(cleaned)
            claims.append(cleaned)

    for item in output.fact_checks:
        _add(item.claim)

    for claim in extract_claims_from_text(worker_output.content):
        _add(claim)

    if not claims:
        _add(worker_output.summary)

    return claims


def _truncate(text: str, limit: int = 240) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + "…"


_EMPTY_ACK_PHRASES = (
    "无订单",
    "没有订单",
    "暂无订单",
    "无相关订单",
    "空列表",
    "空结果",
    "暂无记录",
    "无记录",
    "0 条",
    "0条",
    "0 个",
    "0个",
    "total=0",
    "total：0",
    "total: 0",
    "total 0",
    "共 0",
    "共0",
    "未找到",
    "无数据",
    "没有数据",
    "暂无数据",
    "无匹配",
    "没有找到",
)


def _is_empty_tool_result(result: str) -> bool:
    """判断工具返回是否表示「空结果」（与 HTTP/业务错误不同）。"""
    stripped = result.strip()
    if not stripped:
        return True
    try:
        data = json.loads(stripped)
    except json.JSONDecodeError:
        return stripped in ("[]", "{}")

    if isinstance(data, list):
        return len(data) == 0

    if isinstance(data, dict):
        total = data.get("total")
        if total == 0:
            return True
        for key in ("orders", "hits", "items", "products", "results", "data"):
            value = data.get(key)
            if isinstance(value, list) and len(value) == 0:
                return True
    return False


def _content_acknowledges_empty_result(text: str) -> bool:
    normalized = text.lower()
    return any(phrase in text or phrase in normalized for phrase in _EMPTY_ACK_PHRASES)


def _content_cites_tool_result(
    content: str,
    result: str,
    *,
    tool_name: str = "",
) -> bool:
    """启发式判断 Worker 正文是否引用了工具返回的关键片段。"""
    if _is_empty_tool_result(result) and _content_acknowledges_empty_result(content):
        return True

    if tool_name and _is_empty_tool_result(result):
        logic = normalize_tool_name(tool_name)
        if logic and logic in content.lower().replace("-", "_"):
            return _content_acknowledges_empty_result(content)

    content_lower = content.lower()
    if "http://" in content_lower or "https://" in content_lower:
        return True
    for line in result.splitlines():
        snippet = line.strip()
        if len(snippet) >= 8 and snippet in content:
            return True
    for token in result.split():
        if len(token) >= 6 and token in content:
            return True
    return False


def _build_tool_error_feedback(tool_checks: list[ToolCheckItem]) -> str:
    lines = ["以下工具调用返回错误，请修正后重试："]
    for item in tool_checks:
        if item.status == "failed":
            detail = f" — {item.detail}" if item.detail else ""
            lines.append(f"- {item.tool_name}{detail}")
    return "\n".join(lines)


def _build_uncited_feedback(tool_checks: list[ToolCheckItem]) -> str:
    lines = ["Worker 使用了外部工具但未在 content 中引用关键结果，请补充来源与数据："]
    for item in tool_checks:
        if item.status == "uncited":
            lines.append(f"- {item.tool_name}")
    return "\n".join(lines)


def apply_tool_verification(
    output: CriticOutput,
    worker_output: WorkerOutput,
) -> CriticOutput:
    """校验 Worker 工具调用：失败返回驳回；外部工具成功但未引用则驳回。"""
    if not worker_output.tool_invocations:
        return output

    combined_text = f"{worker_output.content}\n{worker_output.summary}".strip()
    tool_checks: list[ToolCheckItem] = []
    failed: list[ToolCheckItem] = []
    uncited: list[ToolCheckItem] = []

    for inv in worker_output.tool_invocations:
        logic_name = normalize_tool_name(inv.tool_name)
        error = inv.error or is_tool_result_error(inv.tool_name, inv.result)
        if error:
            item = ToolCheckItem(
                tool_name=logic_name,
                status="failed",
                detail=_truncate(inv.result),
            )
            failed.append(item)
        elif logic_name in _EXTERNAL_TOOLS and not _content_cites_tool_result(
            combined_text, inv.result, tool_name=logic_name
        ):
            item = ToolCheckItem(
                tool_name=logic_name,
                status="uncited",
                detail=_truncate(inv.result),
            )
            uncited.append(item)
        else:
            item = ToolCheckItem(
                tool_name=logic_name,
                status="ok",
                detail=_truncate(inv.result),
            )
        tool_checks.append(item)

    passed = output.passed and not failed and not uncited
    feedback = output.feedback
    confidence = output.confidence

    if failed and not feedback:
        feedback = _build_tool_error_feedback(tool_checks)
        confidence = min(confidence, 0.3)
    elif uncited and not feedback:
        feedback = _build_uncited_feedback(tool_checks)
        confidence = min(confidence, 0.5)

    return output.model_copy(
        update={
            "tool_checks": tool_checks,
            "passed": passed,
            "feedback": feedback,
            "confidence": confidence,
        }
    )


async def apply_hereness_verification(
    output: CriticOutput,
    *,
    middleware: ReadOnlyMiddleware,
    user_id: str,
    worker_output: WorkerOutput,
) -> CriticOutput:
    """查询信念库并对齐 fact_checks；发现矛盾则驳回。"""
    claims = collect_claims_for_verification(output, worker_output)
    if not claims:
        return output

    belief_results = await middleware.query_beliefs(user_id, claims)
    fact_checks = _merge_fact_checks(output.fact_checks, belief_results)
    contradicted = [item for item in fact_checks if item.status == "contradicted"]

    passed = output.passed and not contradicted
    feedback = output.feedback
    if contradicted and not feedback:
        feedback = _build_contradiction_feedback(fact_checks)

    confidence = output.confidence
    if contradicted:
        confidence = min(confidence, 0.4)

    return output.model_copy(
        update={
            "fact_checks": fact_checks,
            "passed": passed,
            "feedback": feedback,
            "confidence": confidence,
        }
    )
