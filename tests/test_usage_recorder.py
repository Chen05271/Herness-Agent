"""usage_recorder 单元测试。"""

from unittest.mock import AsyncMock

import pytest

from herness.models.task import TaskStatus, TokenUsage
from herness.models.usage import UsageSource
from herness.observability.usage_recorder import (
    bind_usage_store,
    record_usage_event,
    usage_from_embedding_response,
)
from herness.observability.usage_store import InMemoryUsageStore


def test_usage_from_embedding_response_prompt_tokens() -> None:
    usage = usage_from_embedding_response(
        {"usage": {"prompt_tokens": 12, "total_tokens": 12}}
    )
    assert usage is not None
    assert usage.input_tokens == 12
    assert usage.output_tokens == 0
    assert usage.total_tokens == 12
    assert usage.requests == 1


def test_usage_from_embedding_response_input_tokens_alias() -> None:
    usage = usage_from_embedding_response(
        {"usage": {"input_tokens": 8, "total_tokens": 10}}
    )
    assert usage is not None
    assert usage.input_tokens == 8
    assert usage.output_tokens == 2


def test_usage_from_embedding_response_returns_none_for_empty() -> None:
    assert usage_from_embedding_response({}) is None
    assert usage_from_embedding_response({"usage": {"total_tokens": 0}}) is None


async def test_record_usage_event_skips_zero_usage() -> None:
    store = InMemoryUsageStore()
    bind_usage_store(store, metrics_enabled=False)
    try:
        await record_usage_event(
            source=UsageSource.EMBEDDING,
            usage=TokenUsage(),
            user_id="u1",
            session_id="s1",
        )
        assert (await store.get_session_usage("u1", "s1")).total_tokens == 0
    finally:
        bind_usage_store(None)


async def test_record_usage_event_persists_to_store() -> None:
    store = InMemoryUsageStore()
    bind_usage_store(store, metrics_enabled=False)
    try:
        usage = TokenUsage(input_tokens=30, output_tokens=10, total_tokens=40, requests=1)
        await record_usage_event(
            source=UsageSource.RAG,
            usage=usage,
            user_id="u1",
            session_id="sess-rag",
            event_id="rag-event-1",
        )
        session_usage = await store.get_session_usage("u1", "sess-rag")
        assert session_usage.total_tokens == 40
        user_usage = await store.get_user_usage("u1")
        assert user_usage.total_tokens == 40
    finally:
        bind_usage_store(None)


async def test_record_usage_event_swallows_store_errors() -> None:
    failing = AsyncMock()
    failing.record_task_usage = AsyncMock(side_effect=RuntimeError("db down"))
    bind_usage_store(failing, metrics_enabled=False)
    try:
        await record_usage_event(
            source=UsageSource.DREAMING,
            usage=TokenUsage(input_tokens=1, output_tokens=1, total_tokens=2, requests=1),
            user_id="u1",
            event_id="e1",
            status=TaskStatus.COMPLETED,
        )
    finally:
        bind_usage_store(None)

    failing.record_task_usage.assert_awaited_once()
