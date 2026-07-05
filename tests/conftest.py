"""共享测试 fixture — mock Agent，不依赖真实 LLM。"""

from dataclasses import dataclass
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from herness.config import Settings
from herness.middleware.stub import InMemoryMiddleware
from herness.models.task import OrchestratorConfig
from herness.orchestrator.scheduler import Orchestrator


@dataclass
class FakeRunResult:
    """模拟 pydantic_ai RunResult。"""

    output: Any


@pytest.fixture
def middleware() -> InMemoryMiddleware:
    return InMemoryMiddleware()


@pytest.fixture
def test_settings() -> Settings:
    return Settings(
        max_rounds=5,
        step_timeout_seconds=5.0,
        task_timeout_seconds=30.0,
        max_retries_per_step=2,
    )


@pytest.fixture
def test_config(test_settings: Settings) -> OrchestratorConfig:
    return OrchestratorConfig(
        max_rounds=test_settings.max_rounds,
        step_timeout_seconds=test_settings.step_timeout_seconds,
        task_timeout_seconds=test_settings.task_timeout_seconds,
        max_retries_per_step=test_settings.max_retries_per_step,
        max_parallel_workers=test_settings.max_parallel_workers,
    )


def make_mock_agent() -> MagicMock:
    """创建带 AsyncMock run 方法的假 Agent。"""
    agent = MagicMock()
    agent.run = AsyncMock()
    return agent


@pytest.fixture
def mock_agents() -> tuple[MagicMock, MagicMock, MagicMock]:
    return make_mock_agent(), make_mock_agent(), make_mock_agent()


@pytest.fixture
def orchestrator(
    middleware: InMemoryMiddleware,
    test_settings: Settings,
    test_config: OrchestratorConfig,
    mock_agents: tuple[MagicMock, MagicMock, MagicMock],
) -> Orchestrator:
    supervisor, worker, critic = mock_agents
    return Orchestrator(
        middleware=middleware,
        settings=test_settings,
        config=test_config,
        supervisor=supervisor,
        worker=worker,
        critic=critic,
    )
