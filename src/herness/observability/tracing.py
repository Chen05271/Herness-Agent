"""OpenTelemetry tracing — OTLP export aligned with task_id / trace_id."""

from __future__ import annotations

import logging
import uuid
from contextlib import contextmanager
from typing import Any, Iterator

from herness.config import Settings

logger = logging.getLogger(__name__)

_OTEL_READY = False
_tracer: Any | None = None
_provider: Any | None = None


class _NoopSpan:
    """Fallback span when OTEL is disabled or unavailable."""

    def set_attribute(self, key: str, value: Any) -> None:
        return None

    def set_status(self, *args: Any, **kwargs: Any) -> None:
        return None

    def record_exception(self, *args: Any, **kwargs: Any) -> None:
        return None

    def end(self) -> None:
        return None

    def __enter__(self) -> _NoopSpan:
        return self

    def __exit__(self, *args: Any) -> None:
        return None


def is_tracing_enabled() -> bool:
    return _OTEL_READY


def setup_tracing(settings: Settings) -> None:
    """Initialize TracerProvider and exporters when OTEL_ENABLED=true."""
    global _OTEL_READY, _tracer, _provider

    if not settings.otel_enabled:
        return
    if _OTEL_READY:
        return

    try:
        from opentelemetry import trace
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
    except ImportError as exc:
        logger.error(
            "OTEL_ENABLED=true 但未安装 OpenTelemetry 依赖，请执行: "
            'pip install -e ".[otel]" (%s)',
            exc,
        )
        return

    resource = Resource.create(
        {
            "service.name": settings.otel_service_name,
            "service.version": "0.1.0",
        }
    )
    provider = TracerProvider(resource=resource)
    exporter = _build_exporter(settings)
    if exporter is not None:
        provider.add_span_processor(BatchSpanProcessor(exporter))

    trace.set_tracer_provider(provider)
    _provider = provider
    _tracer = trace.get_tracer("herness")
    _OTEL_READY = True

    _instrument_libraries(settings)
    logger.info(
        "OpenTelemetry tracing enabled service=%s exporter=%s",
        settings.otel_service_name,
        settings.otel_exporter,
    )


def shutdown_tracing() -> None:
    """Flush and shut down the tracer provider."""
    global _OTEL_READY, _tracer, _provider

    if _provider is None:
        return

    try:
        _provider.shutdown()
    except Exception:
        logger.exception("OpenTelemetry shutdown failed")
    finally:
        _OTEL_READY = False
        _tracer = None
        _provider = None


def instrument_fastapi_app(app: Any) -> None:
    """Attach FastAPI auto-instrumentation after app creation."""
    if not _OTEL_READY:
        return
    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    except ImportError:
        logger.warning("opentelemetry-instrumentation-fastapi 未安装，跳过 HTTP 自动埋点")
        return

    FastAPIInstrumentor.instrument_app(
        app,
        excluded_urls="health,metrics",
    )


def trace_id_from_task_id(task_id: str) -> int:
    """Map task UUID to a 128-bit OpenTelemetry trace_id."""
    return int(uuid.UUID(task_id).int)


def _build_exporter(settings: Settings) -> Any | None:
    exporter_name = settings.otel_exporter.strip().lower()

    if exporter_name == "console":
        from opentelemetry.sdk.trace.export import ConsoleSpanExporter

        return ConsoleSpanExporter()

    if exporter_name in {"otlp_http", "otlp"}:
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
            OTLPSpanExporter,
        )

        endpoint = settings.otel_endpoint.strip() or "http://localhost:4318/v1/traces"
        return OTLPSpanExporter(endpoint=endpoint)

    if exporter_name == "otlp_grpc":
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
            OTLPSpanExporter,
        )

        endpoint = settings.otel_endpoint.strip() or "localhost:4317"
        return OTLPSpanExporter(endpoint=endpoint, insecure=settings.otel_insecure)

    logger.warning("未知 OTEL_EXPORTER=%s，回退到 console exporter", exporter_name)
    from opentelemetry.sdk.trace.export import ConsoleSpanExporter

    return ConsoleSpanExporter()


def _instrument_libraries(settings: Settings) -> None:
    if not settings.otel_instrument_httpx:
        return
    try:
        from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
    except ImportError:
        logger.warning("opentelemetry-instrumentation-httpx 未安装，跳过 httpx 自动埋点")
        return
    HTTPXClientInstrumentor().instrument()


def _normalize_attributes(attributes: dict[str, Any] | None) -> dict[str, Any]:
    if not attributes:
        return {}
    normalized: dict[str, Any] = {}
    for key, value in attributes.items():
        if value is None:
            continue
        if isinstance(value, (str, int, float, bool)):
            normalized[key] = value
        else:
            normalized[key] = str(value)
    return normalized


@contextmanager
def start_span(
    name: str,
    *,
    attributes: dict[str, Any] | None = None,
    task_id: str | None = None,
) -> Iterator[Any]:
    """Start a span; when task_id is set, align OTEL trace_id with task UUID."""
    if not _OTEL_READY or _tracer is None:
        yield _NoopSpan()
        return

    from opentelemetry import context as otel_context
    from opentelemetry import trace
    from opentelemetry.trace import NonRecordingSpan, SpanContext, TraceFlags

    parent_ctx = otel_context.get_current()
    if task_id:
        trace_id = trace_id_from_task_id(task_id)
        span_id = trace_id & ((1 << 64) - 1)
        if span_id == 0:
            span_id = 1
        remote_ctx = SpanContext(
            trace_id=trace_id,
            span_id=span_id,
            is_remote=True,
            trace_flags=TraceFlags(0x01),
        )
        parent_ctx = trace.set_span_in_context(NonRecordingSpan(remote_ctx))

    attrs = _normalize_attributes(attributes)
    if task_id:
        attrs.setdefault("herness.task_id", task_id)

    with _tracer.start_as_current_span(name, context=parent_ctx) as span:
        for key, value in attrs.items():
            span.set_attribute(key, value)
        try:
            yield span
        except Exception as exc:
            span.record_exception(exc)
            try:
                from opentelemetry.trace import StatusCode

                span.set_status(StatusCode.ERROR, str(exc))
            except Exception:
                pass
            raise


def set_span_attributes(attributes: dict[str, Any]) -> None:
    """Attach attributes to the current active span, if any."""
    if not _OTEL_READY:
        return
    try:
        from opentelemetry import trace

        span = trace.get_current_span()
        if span is None or not span.is_recording():
            return
        for key, value in _normalize_attributes(attributes).items():
            span.set_attribute(key, value)
    except Exception:
        return
