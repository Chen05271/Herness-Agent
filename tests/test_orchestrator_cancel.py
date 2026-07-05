"""调度器任务取消测试。"""

import asyncio

import pytest

from herness.models.supervisor import SupervisorAction, SupervisorOutput
from herness.models.task import TaskRequest, TaskStatus
from herness.orchestrator.cancellation import TaskCancellationRegistry
from herness.orchestrator.scheduler import Orchestrator
from tests.conftest import FakeRunResult


@pytest.mark.asyncio
async def test_orchestrator_cancelled_mid_run(
    middleware,
    test_settings,
    test_config,
    mock_agents,
) -> None:
    supervisor, worker, critic = mock_agents
    registry = TaskCancellationRegistry()

    async def slow_supervisor(*args, **kwargs):
        await asyncio.sleep(0.05)
        registry.request_cancel("cancel-task")
        await asyncio.sleep(0.2)
        return FakeRunResult(
            SupervisorOutput(
                action=SupervisorAction.COMPLETE,
                reasoning="不应到达",
                final_answer="不应完成",
            )
        )

    supervisor.run.side_effect = slow_supervisor

    orchestrator = Orchestrator(
        middleware=middleware,
        settings=test_settings,
        config=test_config,
        supervisor=supervisor,
        worker=worker,
        critic=critic,
        cancellation_registry=registry,
    )

    result = await orchestrator.run(
        TaskRequest(user_id="u1", input="取消测试", task_id="cancel-task")
    )

    assert result.status == TaskStatus.CANCELLED
    assert result.error == "任务已取消"


@pytest.mark.asyncio
async def test_orchestrator_on_message_callback(
    middleware,
    test_settings,
    test_config,
    mock_agents,
) -> None:
    supervisor, worker, critic = mock_agents
    messages: list = []

    supervisor.run.side_effect = [
        FakeRunResult(
            SupervisorOutput(
                action=SupervisorAction.COMPLETE,
                reasoning="完成",
                final_answer="答案",
            )
        ),
    ]

    orchestrator = Orchestrator(
        middleware=middleware,
        settings=test_settings,
        config=test_config,
        supervisor=supervisor,
        worker=worker,
        critic=critic,
    )

    result = await orchestrator.run(
        TaskRequest(user_id="u1", input="消息测试", task_id="msg-task"),
        on_message=messages.append,
    )

    assert result.status == TaskStatus.COMPLETED
    assert len(messages) >= 1
