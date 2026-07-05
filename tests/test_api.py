"""HTTP API 集成测试 — P1-1 FastAPI 入口。"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from herness.api.app import create_app
from herness.api.store import TaskStore
from herness.middleware.stub import InMemoryMiddleware
from herness.models.supervisor import SupervisorAction, SupervisorOutput
from herness.models.task import TaskStatus
from herness.orchestrator.scheduler import Orchestrator
from tests.conftest import FakeRunResult


@pytest.fixture
def mock_orchestrator(
    middleware,
    test_settings,
    test_config,
    mock_agents,
) -> Orchestrator:
    supervisor, worker, critic = mock_agents
    supervisor.run.side_effect = [
        FakeRunResult(
            SupervisorOutput(
                action=SupervisorAction.COMPLETE,
                reasoning="直接完成",
                final_answer="API 回答",
            )
        ),
    ]
    return Orchestrator(
        middleware=middleware,
        settings=test_settings,
        config=test_config,
        supervisor=supervisor,
        worker=worker,
        critic=critic,
    )


@pytest.fixture
def api_client(mock_orchestrator: Orchestrator) -> TestClient:
    store = TaskStore()
    app = create_app(
        orchestrator=mock_orchestrator,
        store=store,
        middleware=InMemoryMiddleware(),
    )
    with TestClient(app) as client:
        yield client


def test_health(api_client: TestClient) -> None:
    response = api_client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_metrics_endpoint(api_client: TestClient) -> None:
    before = api_client.get("/metrics").json()
    assert "tasks_total" in before
    assert "critic_rejections_total" in before
    assert "dreaming_jobs" in before
    before_completed = before["tasks_total"].get("completed", 0)

    api_client.post("/v1/tasks", json={"user_id": "u1", "input": "metrics test"})
    after = api_client.get("/metrics").json()
    assert after["tasks_total"].get("completed", 0) == before_completed + 1


def test_submit_and_get_task(api_client: TestClient) -> None:
    submit = api_client.post(
        "/v1/tasks",
        json={"user_id": "u1", "input": "你好"},
    )
    assert submit.status_code == 202
    body = submit.json()
    task_id = body["task_id"]
    assert body["status"] == TaskStatus.PENDING.value

    status_resp = api_client.get(f"/v1/tasks/{task_id}")
    assert status_resp.status_code == 200
    status_body = status_resp.json()
    assert status_body["task_id"] == task_id
    assert status_body["status"] == TaskStatus.COMPLETED.value
    assert status_body["answer"] == "API 回答"


def test_get_task_messages(api_client: TestClient) -> None:
    submit = api_client.post(
        "/v1/tasks",
        json={"user_id": "u1", "input": "审计日志测试"},
    )
    task_id = submit.json()["task_id"]

    messages_resp = api_client.get(f"/v1/tasks/{task_id}/messages")
    assert messages_resp.status_code == 200
    messages_body = messages_resp.json()
    assert messages_body["task_id"] == task_id
    assert len(messages_body["messages"]) >= 1


def test_get_task_not_found(api_client: TestClient) -> None:
    response = api_client.get("/v1/tasks/nonexistent")
    assert response.status_code == 404


def test_execute_task_failure_stores_failed(
    middleware,
    test_settings,
    test_config,
) -> None:
    """后台执行异常时，任务终态为 FAILED。"""
    orchestrator = MagicMock(spec=Orchestrator)
    orchestrator.run = AsyncMock(side_effect=RuntimeError("boom"))
    store = TaskStore()
    app = create_app(
        orchestrator=orchestrator,
        store=store,
        middleware=InMemoryMiddleware(),
    )

    with TestClient(app) as client:
        submit = client.post("/v1/tasks", json={"user_id": "u1", "input": "fail"})
        task_id = submit.json()["task_id"]
        status = client.get(f"/v1/tasks/{task_id}").json()
        assert status["status"] == TaskStatus.FAILED.value
        assert status["error"] == "任务执行异常"
