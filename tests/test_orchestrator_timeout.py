"""调度器超时测试。"""

import asyncio
from unittest.mock import MagicMock


from herness.config import Settings
from herness.middleware.stub import InMemoryMiddleware
from herness.models.task import OrchestratorConfig, TaskRequest, TaskStatus
from herness.orchestrator.scheduler import Orchestrator


async def test_task_timeout(
    mock_agents: tuple[MagicMock, MagicMock, MagicMock],
) -> None:
    """整任务超时返回 TIMEOUT 状态。"""
    supervisor, worker, critic = mock_agents

    async def slow_supervisor(*_args, **_kwargs):
        await asyncio.sleep(2)
        return MagicMock()

    supervisor.run = slow_supervisor

    orchestrator = Orchestrator(
        middleware=InMemoryMiddleware(),
        settings=Settings(
            max_rounds=3,
            step_timeout_seconds=5.0,
            task_timeout_seconds=0.3,
            max_retries_per_step=0,
        ),
        config=OrchestratorConfig(
            max_rounds=3,
            step_timeout_seconds=5.0,
            task_timeout_seconds=0.3,
            max_retries_per_step=0,
        ),
        supervisor=supervisor,
        worker=worker,
        critic=critic,
    )

    result = await orchestrator.run(TaskRequest(user_id="u1", input="test"))

    assert result.status == TaskStatus.TIMEOUT
    assert result.error == "任务超时"
