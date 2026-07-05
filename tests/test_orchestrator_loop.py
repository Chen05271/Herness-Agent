"""调度器循环规划检测测试。"""

from unittest.mock import MagicMock

import pytest

from herness.models.critic import CriticOutput
from herness.models.supervisor import SupervisorAction, SupervisorOutput
from herness.models.task import TaskRequest, TaskStatus
from herness.models.worker import WorkerOutput
from herness.orchestrator.scheduler import Orchestrator
from tests.conftest import FakeRunResult


async def test_loop_detection_same_plan(
    orchestrator: Orchestrator,
    mock_agents: tuple[MagicMock, MagicMock, MagicMock],
) -> None:
    """相同 action + instruction + reasoning 重复出现时中止。"""
    supervisor, worker, critic = mock_agents

    same_plan = SupervisorOutput(
        action=SupervisorAction.DELEGATE,
        reasoning="同样规划",
        task_instruction="同样指令",
    )
    supervisor.run.return_value = FakeRunResult(same_plan)
    worker.run.return_value = FakeRunResult(
        WorkerOutput(content="x", summary="y", needs_verification=True)
    )
    critic.run.return_value = FakeRunResult(
        CriticOutput(passed=False, feedback="驳回")
    )

    result = await orchestrator.run(TaskRequest(user_id="u1", input="test"))

    assert result.status == TaskStatus.FAILED
    assert "循环规划" in result.error


async def test_max_rounds_exceeded(
    orchestrator: Orchestrator,
    mock_agents: tuple[MagicMock, MagicMock, MagicMock],
) -> None:
    """超过 max_rounds 时失败。"""
    supervisor, worker, critic = mock_agents
    round_counter = {"n": 0}

    def next_delegate(*_args, **_kwargs):
        round_counter["n"] += 1
        return FakeRunResult(
            SupervisorOutput(
                action=SupervisorAction.DELEGATE,
                reasoning=f"轮次 {round_counter['n']}",
                task_instruction=f"指令 {round_counter['n']}",
            )
        )

    supervisor.run.side_effect = next_delegate
    worker.run.return_value = FakeRunResult(
        WorkerOutput(content="x", summary="y", needs_verification=False)
    )

    result = await orchestrator.run(TaskRequest(user_id="u1", input="test"))

    assert result.status == TaskStatus.FAILED
    assert "超过最大轮数" in result.error
