"""Token 用量持久化与 session 汇总 API 测试。"""

from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from herness.api.app import create_app
from herness.api.store import TaskStore
from herness.config import Settings
from herness.middleware.stub import InMemoryMiddleware
from herness.models.supervisor import SupervisorAction, SupervisorOutput
from herness.models.task import TaskRequest, TaskStatus, TokenUsage
from herness.observability.usage_store import InMemoryUsageStore
from herness.orchestrator.scheduler import Orchestrator
from pydantic_ai.usage import RunUsage
from tests.conftest import FakeRunResult


@pytest.fixture
def usage_api_client(
    middleware,
    test_settings: Settings,
    test_config,
    mock_agents,
) -> TestClient:
    supervisor, worker, critic = mock_agents
    supervisor.run.return_value = FakeRunResult(
        SupervisorOutput(
            action=SupervisorAction.COMPLETE,
            reasoning="完成",
            final_answer="ok",
        ),
        usage=RunUsage(input_tokens=100, output_tokens=40, requests=1),
    )
    orchestrator = Orchestrator(
        middleware=middleware,
        settings=test_settings,
        config=test_config,
        supervisor=supervisor,
        worker=worker,
        critic=critic,
    )
    app = create_app(
        settings=test_settings,
        orchestrator=orchestrator,
        store=TaskStore(),
        middleware=InMemoryMiddleware(),
        usage_store=InMemoryUsageStore(),
    )
    with TestClient(app) as client:
        yield client


async def test_in_memory_usage_store_session_aggregate() -> None:
    store = InMemoryUsageStore()
    first = TokenUsage(input_tokens=100, output_tokens=40, total_tokens=140, requests=1)
    second = TokenUsage(input_tokens=50, output_tokens=20, total_tokens=70, requests=1)

    await store.record_task_usage(
        task_id="t1",
        user_id="u1",
        session_id="s1",
        status=TaskStatus.COMPLETED,
        usage=first,
    )
    await store.record_task_usage(
        task_id="t2",
        user_id="u1",
        session_id="s1",
        status=TaskStatus.COMPLETED,
        usage=second,
    )

    session_usage = await store.get_session_usage("u1", "s1")
    assert session_usage.input_tokens == 150
    assert session_usage.output_tokens == 60
    assert session_usage.total_tokens == 210
    assert session_usage.requests == 2

    user_usage = await store.get_user_usage("u1")
    assert user_usage.total_tokens == 210


async def test_in_memory_usage_store_upsert_replaces_task() -> None:
    store = InMemoryUsageStore()
    original = TokenUsage(input_tokens=100, output_tokens=40, total_tokens=140, requests=1)
    updated = TokenUsage(input_tokens=30, output_tokens=10, total_tokens=40, requests=1)

    await store.record_task_usage(
        task_id="t1",
        user_id="u1",
        session_id="s1",
        status=TaskStatus.COMPLETED,
        usage=original,
    )
    await store.record_task_usage(
        task_id="t1",
        user_id="u1",
        session_id="s1",
        status=TaskStatus.COMPLETED,
        usage=updated,
    )

    session_usage = await store.get_session_usage("u1", "s1")
    assert session_usage.total_tokens == 40


async def test_in_memory_usage_store_isolates_sessions_and_users() -> None:
    store = InMemoryUsageStore()
    usage = TokenUsage(input_tokens=10, output_tokens=5, total_tokens=15, requests=1)

    await store.record_task_usage(
        task_id="t1",
        user_id="u1",
        session_id="s1",
        status=TaskStatus.COMPLETED,
        usage=usage,
    )
    await store.record_task_usage(
        task_id="t2",
        user_id="u1",
        session_id="s2",
        status=TaskStatus.COMPLETED,
        usage=usage,
    )
    await store.record_task_usage(
        task_id="t3",
        user_id="u2",
        session_id="s1",
        status=TaskStatus.COMPLETED,
        usage=usage,
    )

    assert (await store.get_session_usage("u1", "s1")).total_tokens == 15
    assert (await store.get_user_usage("u1")).total_tokens == 30
    assert (await store.get_user_usage("u2")).total_tokens == 15
    assert (await store.get_session_usage("u1", "missing")).total_tokens == 0


def test_session_usage_endpoint(usage_api_client: TestClient) -> None:
    submit = usage_api_client.post(
        "/v1/tasks",
        json={
            "user_id": "u1",
            "session_id": "sess-1",
            "input": "hello",
        },
    )
    assert submit.status_code == 202
    task_id = submit.json()["task_id"]

    status = usage_api_client.get(f"/v1/tasks/{task_id}").json()
    assert status["status"] == TaskStatus.COMPLETED.value
    assert status["usage"]["total_tokens"] == 140

    usage = usage_api_client.get(
        "/v1/sessions/consumer-u1:sess-1/usage",
        params={"user_id": "u1"},
    ).json()
    assert usage["session_id"] == "consumer-u1:sess-1"
    assert usage["usage"]["input_tokens"] == 100
    assert usage["usage"]["output_tokens"] == 40


async def test_in_memory_usage_store_multiple_sources_accumulate() -> None:
    """同一 task 的不同 source（如 orchestrator / dreaming）应分别计入汇总。"""
    store = InMemoryUsageStore()
    orchestrator_usage = TokenUsage(input_tokens=100, output_tokens=40, total_tokens=140, requests=1)
    dreaming_usage = TokenUsage(input_tokens=20, output_tokens=10, total_tokens=30, requests=1)

    await store.record_task_usage(
        task_id="t1",
        user_id="u1",
        session_id="s1",
        status=TaskStatus.COMPLETED,
        usage=orchestrator_usage,
        source="orchestrator",
    )
    await store.record_task_usage(
        task_id="t1",
        user_id="u1",
        session_id="s1",
        status=TaskStatus.COMPLETED,
        usage=dreaming_usage,
        source="dreaming",
    )

    session_usage = await store.get_session_usage("u1", "s1")
    assert session_usage.total_tokens == 170


@pytest.fixture
def zero_usage_api_client(
    middleware,
    test_settings: Settings,
    test_config,
    mock_agents,
) -> TestClient:
    supervisor, worker, critic = mock_agents
    supervisor.run.return_value = FakeRunResult(
        SupervisorOutput(
            action=SupervisorAction.COMPLETE,
            reasoning="完成",
            final_answer="ok",
        ),
    )
    orchestrator = Orchestrator(
        middleware=middleware,
        settings=test_settings,
        config=test_config,
        supervisor=supervisor,
        worker=worker,
        critic=critic,
    )
    app = create_app(
        settings=test_settings,
        orchestrator=orchestrator,
        store=TaskStore(),
        middleware=InMemoryMiddleware(),
        usage_store=InMemoryUsageStore(),
    )
    with TestClient(app) as client:
        yield client


def test_zero_usage_not_persisted_to_session(
    zero_usage_api_client: TestClient,
) -> None:
    submit = zero_usage_api_client.post(
        "/v1/tasks",
        json={
            "user_id": "u1",
            "session_id": "sess-zero",
            "input": "hello",
        },
    )
    task_id = submit.json()["task_id"]
    status = zero_usage_api_client.get(f"/v1/tasks/{task_id}").json()
    assert status["usage"]["total_tokens"] == 0

    usage = zero_usage_api_client.get(
        "/v1/sessions/consumer-u1:sess-zero/usage",
        params={"user_id": "u1"},
    ).json()
    assert usage["usage"]["total_tokens"] == 0


def test_session_usage_accumulates_multiple_tasks(usage_api_client: TestClient) -> None:
    session_id = "sess-multi"
    for _ in range(2):
        submit = usage_api_client.post(
            "/v1/tasks",
            json={
                "user_id": "u1",
                "session_id": session_id,
                "input": "hello",
            },
        )
        assert submit.status_code == 202
        task_id = submit.json()["task_id"]
        status = usage_api_client.get(f"/v1/tasks/{task_id}").json()
        assert status["status"] == TaskStatus.COMPLETED.value

    usage = usage_api_client.get(
        f"/v1/sessions/consumer-u1:{session_id}/usage",
        params={"user_id": "u1"},
    ).json()
    assert usage["usage"]["input_tokens"] == 200
    assert usage["usage"]["output_tokens"] == 80
    assert usage["usage"]["total_tokens"] == 280


async def test_orchestrator_startup_failure_returns_failed_without_raising(
    middleware,
    test_settings,
    test_config,
    mock_agents,
) -> None:
    """任务启动阶段异常应返回 FAILED，而不是抛到 API 层。"""
    supervisor, worker, critic = mock_agents
    middleware.get_pre_synthesized_memory = AsyncMock(
        side_effect=RuntimeError("memory unavailable"),
    )
    orchestrator = Orchestrator(
        middleware=middleware,
        settings=test_settings,
        config=test_config,
        supervisor=supervisor,
        worker=worker,
        critic=critic,
    )

    result = await orchestrator.run(TaskRequest(user_id="u1", input="hello"))

    assert result.status == TaskStatus.FAILED
    assert "memory unavailable" in result.error
    assert result.usage.total_tokens == 0


@pytest.fixture
def session_budget_api_client(
    middleware,
    mock_agents,
    test_config,
) -> TestClient:
    supervisor, worker, critic = mock_agents
    supervisor.run.return_value = FakeRunResult(
        SupervisorOutput(
            action=SupervisorAction.COMPLETE,
            reasoning="完成",
            final_answer="ok",
        ),
        usage=RunUsage(input_tokens=100, output_tokens=40, requests=1),
    )
    settings = Settings(
        max_rounds=5,
        step_timeout_seconds=5.0,
        task_timeout_seconds=30.0,
        max_retries_per_step=2,
        api_key="",
        token_budget_per_session=100,
    )
    orchestrator = Orchestrator(
        middleware=middleware,
        settings=settings,
        config=test_config,
        supervisor=supervisor,
        worker=worker,
        critic=critic,
    )
    app = create_app(
        settings=settings,
        orchestrator=orchestrator,
        store=TaskStore(),
        middleware=InMemoryMiddleware(),
        usage_store=InMemoryUsageStore(),
    )
    with TestClient(app) as client:
        yield client


def test_session_token_budget_returns_429_after_limit(
    session_budget_api_client: TestClient,
) -> None:
    session_id = "consumer-u1:sess-budget"
    first = session_budget_api_client.post(
        "/v1/tasks",
        json={"user_id": "u1", "session_id": session_id, "input": "hello"},
    )
    assert first.status_code == 202
    task_id = first.json()["task_id"]
    status = session_budget_api_client.get(f"/v1/tasks/{task_id}").json()
    assert status["status"] == TaskStatus.COMPLETED.value

    second = session_budget_api_client.post(
        "/v1/tasks",
        json={"user_id": "u1", "session_id": session_id, "input": "again"},
    )
    assert second.status_code == 429
    assert "会话 token 配额已用尽" in second.json()["detail"]


def test_user_usage_endpoint(usage_api_client: TestClient) -> None:
    submit = usage_api_client.post(
        "/v1/tasks",
        json={"user_id": "u1", "session_id": "sess-user-usage", "input": "hello"},
    )
    assert submit.status_code == 202
    task_id = submit.json()["task_id"]
    status = usage_api_client.get(f"/v1/tasks/{task_id}").json()
    assert status["status"] == TaskStatus.COMPLETED.value

    usage = usage_api_client.get("/v1/users/u1/usage").json()
    assert usage["user_id"] == "u1"
    assert usage["usage"]["total_tokens"] == 140
