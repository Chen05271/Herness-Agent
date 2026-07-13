"""OpenTelemetry tracing 单元测试。"""

import uuid

import pytest

pytest.importorskip("opentelemetry")
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)

from herness.config import Settings
from herness.observability import tracing
from herness.observability.tracing import (
    setup_tracing,
    shutdown_tracing,
    start_span,
    trace_id_from_task_id,
)


@pytest.fixture(autouse=True)
def reset_tracing_state() -> None:
    shutdown_tracing()
    yield
    shutdown_tracing()


def test_trace_id_from_task_id_matches_uuid() -> None:
    task_id = str(uuid.uuid4())
    expected = int(uuid.UUID(task_id).int)
    assert trace_id_from_task_id(task_id) == expected


def test_start_span_noop_when_disabled() -> None:
    with start_span("test.noop", task_id=str(uuid.uuid4())) as span:
        span.set_attribute("herness.ok", True)


def test_start_span_records_child_spans() -> None:
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
    tracing._OTEL_READY = True
    tracing._tracer = trace.get_tracer("herness-test")
    tracing._provider = provider

    task_id = str(uuid.uuid4())
    with start_span(
        "orchestrator.run",
        task_id=task_id,
        attributes={"herness.user_id": "u1"},
    ):
        with start_span("orchestrator.supervisor", attributes={"herness.round_index": 0}):
            pass

    spans = exporter.get_finished_spans()
    assert len(spans) == 2
    root = spans[1]
    child = spans[0]
    assert root.name == "orchestrator.run"
    assert child.name == "orchestrator.supervisor"
    assert root.attributes["herness.task_id"] == task_id
    assert root.context.trace_id == trace_id_from_task_id(task_id)


def test_setup_tracing_enables_flag() -> None:
    settings = Settings(
        otel_enabled=True,
        otel_exporter="console",
        otel_service_name="herness-test",
        _env_file=None,
    )
    setup_tracing(settings)
    assert tracing.is_tracing_enabled()
