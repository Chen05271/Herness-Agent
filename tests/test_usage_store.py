"""Token 用量持久化与 session 汇总 API 测试。"""

import time

import pytest
from fastapi.testclient import TestClient

from herness.api.app import create_app
from herness.api.store import TaskStore
from herness.config import Settings
from herness.middleware.stub import InMemoryMiddleware
from herness.models.supervisor import SupervisorAction, SupervisorOutput
from herness.models.task import TaskStatus
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

    for _ in range(50):
        status = usage_api_client.get(f"/v1/tasks/{task_id}").json()
        if status["status"] == TaskStatus.COMPLETED.value:
            break
        time.sleep(0.05)
    else:
        raise AssertionError("task did not complete")

    assert status["usage"]["total_tokens"] == 140

    usage = usage_api_client.get(
        "/v1/sessions/consumer-u1:sess-1/usage",
        params={"user_id": "u1"},
    ).json()
    assert usage["session_id"] == "consumer-u1:sess-1"
    assert usage["usage"]["input_tokens"] == 100
    assert usage["usage"]["output_tokens"] == 40
