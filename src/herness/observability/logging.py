"""结构化日志 — trace_id 贯穿调度链路。"""

import json
import logging
import sys
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Any

trace_id_var: ContextVar[str | None] = ContextVar("trace_id", default=None)


def set_trace_id(trace_id: str) -> None:
    """设置当前协程的 trace_id（通常等于 task_id）。"""
    trace_id_var.set(trace_id)


def get_trace_id() -> str | None:
    return trace_id_var.get()


def log_event(
    logger: logging.Logger,
    level: int,
    event: str,
    *,
    role: str | None = None,
    round_index: int | None = None,
    **fields: Any,
) -> None:
    """输出 JSON 结构化日志条目。"""
    payload: dict[str, Any] = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event": event,
        "trace_id": get_trace_id(),
    }
    if role is not None:
        payload["role"] = role
    if round_index is not None:
        payload["round_index"] = round_index
    payload.update(fields)
    logger.log(level, json.dumps(payload, ensure_ascii=False))


def configure_logging(*, structured: bool = False, level: int = logging.INFO) -> None:
    """配置根日志：structured=True 时输出纯 JSON 行（配合 log_event）。"""
    root = logging.getLogger()
    root.handlers.clear()
    handler = logging.StreamHandler(sys.stderr)
    if structured:
        handler.setFormatter(logging.Formatter("%(message)s"))
    else:
        handler.setFormatter(
            logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
        )
    root.addHandler(handler)
    root.setLevel(level)
