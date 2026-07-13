"""跨模块 token 用量记录 — API / Dreaming / Embedding 共享。"""

from __future__ import annotations

import logging
from uuid import uuid4

from herness.models.task import TaskStatus, TokenUsage
from herness.models.usage import UsageSource
from herness.observability.metrics import get_metrics_registry
from herness.observability.usage_store import UsageStore

logger = logging.getLogger(__name__)

_usage_store: UsageStore | None = None
_metrics_enabled: bool = True


def bind_usage_store(
    store: UsageStore | None,
    *,
    metrics_enabled: bool = True,
) -> None:
    """绑定进程内用量存储（API / Dreaming Worker 启动时调用）。"""
    global _usage_store, _metrics_enabled
    _usage_store = store
    _metrics_enabled = metrics_enabled


def usage_from_embedding_response(data: dict) -> TokenUsage | None:
    """从 OpenAI 兼容 embeddings 响应提取 token 用量。"""
    raw = data.get("usage")
    if not isinstance(raw, dict):
        return None
    prompt = int(raw.get("prompt_tokens") or raw.get("input_tokens") or 0)
    total = int(raw.get("total_tokens") or prompt)
    if total <= 0 and prompt <= 0:
        return None
    output = max(total - prompt, 0)
    return TokenUsage(
        input_tokens=prompt,
        output_tokens=output,
        total_tokens=total,
        requests=1,
    )


async def record_usage_event(
    *,
    source: UsageSource | str,
    usage: TokenUsage,
    user_id: str = "",
    session_id: str = "",
    event_id: str = "",
    status: TaskStatus = TaskStatus.COMPLETED,
) -> None:
    """写入指标与持久化存储。"""
    if usage.total_tokens <= 0 and usage.requests <= 0:
        return

    source_key = str(source)
    if _metrics_enabled:
        metrics = get_metrics_registry()
        metrics.record_token_usage(
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            requests=usage.requests,
            source=source_key,
        )

    if _usage_store is None:
        return

    resolved_event_id = event_id or f"{source_key}:{uuid4()}"
    try:
        await _usage_store.record_task_usage(
            task_id=resolved_event_id,
            user_id=user_id,
            session_id=session_id,
            status=status,
            usage=usage,
            source=source_key,
        )
    except Exception:
        logger.exception(
            "record_usage_event failed source=%s event_id=%s",
            source_key,
            resolved_event_id,
        )
