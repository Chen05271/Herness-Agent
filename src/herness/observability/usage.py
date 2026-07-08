"""LLM token 用量提取与汇总。"""

from __future__ import annotations

from typing import Any

from pydantic_ai.usage import RunUsage

from herness.models.task import TokenUsage


def usage_from_run(result: Any) -> TokenUsage | None:
    """从 pydantic-ai AgentRunResult 提取 token 用量。"""
    raw = getattr(result, "usage", None)
    if raw is None:
        return None
    return usage_from_run_usage(raw)


def usage_from_run_usage(usage: RunUsage) -> TokenUsage:
    """将 pydantic-ai RunUsage 转为 API 友好的 TokenUsage。"""
    input_tokens = int(usage.input_tokens or 0)
    output_tokens = int(usage.output_tokens or 0)
    return TokenUsage(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=input_tokens + output_tokens,
        requests=int(usage.requests or 0),
        tool_calls=int(usage.tool_calls or 0),
    )


def usage_payload(usage: TokenUsage) -> dict[str, int]:
    """写入 TaskMessage.payload 的精简字段。"""
    return usage.model_dump()
