"""API — SSE 流式日志与任务取消。"""

import asyncio
import json
import threading
import time

import pytest
from fastapi.testclient import TestClient

from herness.api.app import create_app
from herness.api.store import TaskStore
from herness.middleware.stub import InMemoryMiddleware
from herness.models.supervisor import SupervisorAction, SupervisorOutput
from herness.models.task import TaskStatus
from herness.orchestrator.cancellation import TaskCancellationRegistry
from herness.orchestrator.scheduler import Orchestrator
from tests.conftest import FakeRunResult


@pytest.fixture
def slow_orchestrator(
    middleware,
    test_settings,
    test_config,
    mock_agents,
) -> Orchestrator:
    supervisor, worker, critic = mock_agents
    registry = TaskCancellationRegistry()

    async def slow_complete(*args, **kwargs):
        await asyncio.sleep(2.0)
        return FakeRunResult(
            SupervisorOutput(
                action=SupervisorAction.COMPLETE,
                reasoning="完成",
                final_answer="流式回答",
            )
        )

    supervisor.run.side_effect = slow_complete
    return Orchestrator(
        middleware=middleware,
        settings=test_settings,
        config=test_config,
        supervisor=supervisor,
        worker=worker,
        critic=critic,
        cancellation_registry=registry,
    )


@pytest.fixture
def stream_client(slow_orchestrator: Orchestrator) -> TestClient:
    registry = slow_orchestrator._cancellation_registry
    store = TaskStore()
    app = create_app(
        orchestrator=slow_orchestrator,
        store=store,
        middleware=InMemoryMiddleware(),
        cancellation_registry=registry,
    )
    with TestClient(app) as client:
        yield client


def test_cancel_running_task(stream_client: TestClient) -> None:
    task_id = "cancel-running-test"

    def submit() -> None:
        stream_client.post(
            "/v1/tasks",
            json={"user_id": "u1", "input": "running cancel", "task_id": task_id},
        )

    worker = threading.Thread(target=submit)
    worker.start()
    time.sleep(0.1)

    cancel = stream_client.delete(f"/v1/tasks/{task_id}")
    worker.join(timeout=5.0)

    assert cancel.status_code == 200
    assert cancel.json()["status"] == TaskStatus.CANCELLED.value
    assert stream_client.get(f"/v1/tasks/{task_id}").json()["status"] == TaskStatus.CANCELLED.value


def test_sse_stream_receives_messages(stream_client: TestClient) -> None:
    submit = stream_client.post("/v1/tasks", json={"user_id": "u1", "input": "sse test"})
    task_id = submit.json()["task_id"]

    with stream_client.stream("GET", f"/v1/tasks/{task_id}/stream") as response:
        assert response.status_code == 200
        chunks = list(response.iter_lines())
    assert chunks
    payloads = [json.loads(line.removeprefix("data: ")) for line in chunks if line.startswith("data: ")]
    assert any("role" in item for item in payloads)
    assert any(item.get("event") == "task_finished" for item in payloads)


def test_cancel_completed_task_returns_409(stream_client: TestClient) -> None:
    submit = stream_client.post("/v1/tasks", json={"user_id": "u1", "input": "done"})
    task_id = submit.json()["task_id"]
    stream_client.get(f"/v1/tasks/{task_id}")

    response = stream_client.delete(f"/v1/tasks/{task_id}")
    assert response.status_code == 409
