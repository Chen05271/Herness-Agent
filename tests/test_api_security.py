"""API 安全 — 鉴权与 rate limit 测试。"""


import pytest
from fastapi.testclient import TestClient

from herness.api.app import create_app
from herness.api.security import RateLimiter, extract_api_key
from herness.api.store import TaskStore
from herness.config import Settings
from herness.middleware.stub import InMemoryMiddleware
from herness.models.supervisor import SupervisorAction, SupervisorOutput
from herness.orchestrator.scheduler import Orchestrator
from tests.conftest import FakeRunResult


def test_extract_api_key_bearer() -> None:
    assert extract_api_key(authorization="Bearer secret-key", x_api_key=None) == "secret-key"


def test_extract_api_key_header() -> None:
    assert extract_api_key(authorization=None, x_api_key="header-key") == "header-key"


def test_rate_limiter_blocks_over_limit() -> None:
    limiter = RateLimiter(limit=2, window_seconds=60.0)
    assert limiter.check("u1") is True
    assert limiter.check("u1") is True
    assert limiter.check("u1") is False
    assert limiter.check("u2") is True


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
def secured_app(mock_orchestrator: Orchestrator) -> TestClient:
    settings = Settings(api_key="test-secret", rate_limit_per_user=0)
    app = create_app(
        settings=settings,
        orchestrator=mock_orchestrator,
        store=TaskStore(),
        middleware=InMemoryMiddleware(),
    )
    with TestClient(app) as client:
        yield client


@pytest.fixture
def rate_limited_app(mock_orchestrator: Orchestrator) -> TestClient:
    settings = Settings(api_key="", rate_limit_per_user=2, rate_limit_window_seconds=60)
    app = create_app(
        settings=settings,
        orchestrator=mock_orchestrator,
        store=TaskStore(),
        middleware=InMemoryMiddleware(),
    )
    with TestClient(app) as client:
        yield client


def test_api_key_required(secured_app: TestClient) -> None:
    response = secured_app.post("/v1/tasks", json={"user_id": "u1", "input": "hi"})
    assert response.status_code == 401

    ok = secured_app.post(
        "/v1/tasks",
        json={"user_id": "u1", "input": "hi"},
        headers={"Authorization": "Bearer test-secret"},
    )
    assert ok.status_code == 202


def test_api_key_via_x_header(secured_app: TestClient) -> None:
    response = secured_app.post(
        "/v1/tasks",
        json={"user_id": "u1", "input": "hi"},
        headers={"X-API-Key": "test-secret"},
    )
    assert response.status_code == 202


def test_health_unauthenticated_when_api_key_set(secured_app: TestClient) -> None:
    assert secured_app.get("/health").status_code == 200


def test_rate_limit_per_user(rate_limited_app: TestClient) -> None:
    payload = {"user_id": "limited-user", "input": "task"}
    assert rate_limited_app.post("/v1/tasks", json=payload).status_code == 202
    assert rate_limited_app.post("/v1/tasks", json=payload).status_code == 202
    blocked = rate_limited_app.post("/v1/tasks", json=payload)
    assert blocked.status_code == 429

    other = rate_limited_app.post("/v1/tasks", json={"user_id": "other", "input": "ok"})
    assert other.status_code == 202


def test_persona_identity_rejected(secured_app: TestClient) -> None:
    response = secured_app.post(
        "/v1/tasks",
        json={
            "user_id": "user-1",
            "input": "hi",
            "metadata": {"persona": "merchant"},
        },
        headers={"Authorization": "Bearer test-secret"},
    )
    assert response.status_code == 400

    response = secured_app.post(
        "/v1/tasks",
        json={
            "user_id": "merchant:m1:ops:op1",
            "input": "hi",
            "metadata": {"persona": "consumer"},
        },
        headers={"Authorization": "Bearer test-secret"},
    )
    assert response.status_code == 400


def test_get_task_requires_api_key_when_configured(secured_app: TestClient) -> None:
    submit = secured_app.post(
        "/v1/tasks",
        json={"user_id": "u1", "input": "hi"},
        headers={"Authorization": "Bearer test-secret"},
    )
    task_id = submit.json()["task_id"]

    assert secured_app.get(f"/v1/tasks/{task_id}").status_code == 401
    assert (
        secured_app.get(
            f"/v1/tasks/{task_id}",
            headers={"Authorization": "Bearer test-secret"},
        ).status_code
        == 200
    )
