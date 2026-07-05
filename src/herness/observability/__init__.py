"""可观测性模块 — 结构化日志与 trace 上下文。"""

from herness.observability.logging import get_trace_id, log_event, set_trace_id

__all__ = ["get_trace_id", "log_event", "set_trace_id"]
