"""可观测性模块测试 — trace_id 与结构化日志。"""

import json
import logging

from herness.observability.logging import get_trace_id, log_event, set_trace_id


def test_trace_id_context() -> None:
    assert get_trace_id() is None
    set_trace_id("task-abc")
    assert get_trace_id() == "task-abc"


def test_log_event_json_format(caplog) -> None:
    set_trace_id("trace-123")
    test_logger = logging.getLogger("herness.test")

    with caplog.at_level(logging.INFO, logger="herness.test"):
        log_event(
            test_logger,
            logging.INFO,
            "test_event",
            role="orchestrator",
            round_index=0,
            message="hello",
        )

    assert len(caplog.records) == 1
    payload = json.loads(caplog.records[0].message)
    assert payload["event"] == "test_event"
    assert payload["trace_id"] == "trace-123"
    assert payload["role"] == "orchestrator"
    assert payload["message"] == "hello"
