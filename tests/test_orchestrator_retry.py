"""调度器单步重试测试。"""

from unittest.mock import MagicMock


from herness.models.critic import CriticOutput
from herness.models.supervisor import SupervisorAction, SupervisorOutput
from herness.models.task import AgentRole, TaskRequest, TaskStatus
from herness.models.worker import WorkerOutput
from herness.orchestrator.scheduler import Orchestrator
from tests.conftest import FakeRunResult


async def test_worker_retries_on_connection_error(
    orchestrator: Orchestrator,
    mock_agents: tuple[MagicMock, MagicMock, MagicMock],
) -> None:
    """Worker 连接错误时重试，最终成功。"""
    supervisor, worker, critic = mock_agents

    supervisor.run.side_effect = [
        FakeRunResult(
            SupervisorOutput(
                action=SupervisorAction.DELEGATE,
                reasoning="执行",
                task_instruction="任务",
            )
        ),
        FakeRunResult(
            SupervisorOutput(
                action=SupervisorAction.COMPLETE,
                reasoning="完成",
                final_answer="成功",
            )
        ),
    ]
    worker.run.side_effect = [
        ConnectionError("network blip"),
        FakeRunResult(WorkerOutput(content="ok", summary="done", needs_verification=False)),
    ]

    result = await orchestrator.run(TaskRequest(user_id="u1", input="test"))

    assert result.status == TaskStatus.COMPLETED
    assert worker.run.call_count == 2
    retry_logs = [
        m.content for m in result.messages if m.role == AgentRole.ORCHESTRATOR and "重试" in m.content
    ]
    assert len(retry_logs) == 1
    assert "Worker" in retry_logs[0]


async def test_worker_fails_after_max_retries(
    orchestrator: Orchestrator,
    mock_agents: tuple[MagicMock, MagicMock, MagicMock],
) -> None:
    """重试耗尽后任务失败。"""
    supervisor, worker, critic = mock_agents

    supervisor.run.return_value = FakeRunResult(
        SupervisorOutput(
            action=SupervisorAction.DELEGATE,
            reasoning="执行",
            task_instruction="任务",
        )
    )
    worker.run.side_effect = ConnectionError("persistent failure")

    result = await orchestrator.run(TaskRequest(user_id="u1", input="test"))

    assert result.status == TaskStatus.FAILED
    assert "ConnectionError" in result.error
    # max_retries_per_step=2 → 共 3 次尝试
    assert worker.run.call_count == 3


async def test_non_retriable_error_fails_immediately(
    orchestrator: Orchestrator,
    mock_agents: tuple[MagicMock, MagicMock, MagicMock],
) -> None:
    """非瞬时错误不重试，直接失败。"""
    supervisor, worker, critic = mock_agents

    supervisor.run.return_value = FakeRunResult(
        SupervisorOutput(
            action=SupervisorAction.DELEGATE,
            reasoning="执行",
            task_instruction="任务",
        )
    )
    worker.run.side_effect = ValueError("logic error")

    result = await orchestrator.run(TaskRequest(user_id="u1", input="test"))

    assert result.status == TaskStatus.FAILED
    assert "ValueError" in result.error
    assert worker.run.call_count == 1


async def test_critic_retries_on_timeout(
    orchestrator: Orchestrator,
    mock_agents: tuple[MagicMock, MagicMock, MagicMock],
) -> None:
    """Critic 超时时重试。"""
    supervisor, worker, critic = mock_agents

    supervisor.run.side_effect = [
        FakeRunResult(
            SupervisorOutput(
                action=SupervisorAction.DELEGATE,
                reasoning="执行",
                task_instruction="任务",
            )
        ),
        FakeRunResult(
            SupervisorOutput(
                action=SupervisorAction.COMPLETE,
                reasoning="完成",
                final_answer="ok",
            )
        ),
    ]
    worker.run.return_value = FakeRunResult(
        WorkerOutput(content="x", summary="y", needs_verification=True)
    )
    critic.run.side_effect = [
        TimeoutError("step timeout"),
        FakeRunResult(CriticOutput(passed=True, feedback="")),
    ]

    result = await orchestrator.run(TaskRequest(user_id="u1", input="test"))

    assert result.status == TaskStatus.COMPLETED
    assert critic.run.call_count == 2
