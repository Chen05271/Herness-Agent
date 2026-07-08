"""Token 用量采集测试。"""

from unittest.mock import MagicMock

from pydantic_ai.usage import RunUsage

from herness.models.critic import CriticOutput
from herness.models.supervisor import SupervisorAction, SupervisorOutput
from herness.models.task import TaskStatus
from herness.models.worker import WorkerOutput
from herness.observability.metrics import reset_metrics_registry
from herness.observability.usage import usage_from_run_usage, usage_payload
from herness.orchestrator.scheduler import Orchestrator
from tests.conftest import FakeRunResult


def test_usage_from_run_usage() -> None:
    usage = usage_from_run_usage(RunUsage(input_tokens=120, output_tokens=45, requests=1))
    assert usage.input_tokens == 120
    assert usage.output_tokens == 45
    assert usage.total_tokens == 165
    assert usage_payload(usage)["total_tokens"] == 165


async def test_orchestrator_records_token_usage(
    orchestrator: Orchestrator,
    mock_agents: tuple[MagicMock, MagicMock, MagicMock],
) -> None:
    """Supervisor / Worker / Critic 的 usage 应汇总到 TaskResult 与审计 payload。"""
    reset_metrics_registry()
    supervisor, worker, critic = mock_agents

    supervisor.run.side_effect = [
        FakeRunResult(
            SupervisorOutput(
                action=SupervisorAction.DELEGATE,
                reasoning="需要执行",
                task_instruction="写一段介绍",
            ),
            usage=RunUsage(input_tokens=100, output_tokens=20, requests=1),
        ),
        FakeRunResult(
            SupervisorOutput(
                action=SupervisorAction.COMPLETE,
                reasoning="校验通过",
                final_answer="完成。",
            ),
            usage=RunUsage(input_tokens=80, output_tokens=30, requests=1),
        ),
    ]
    worker.run.return_value = FakeRunResult(
        WorkerOutput(content="内容", summary="已撰写", needs_verification=True),
        usage=RunUsage(input_tokens=200, output_tokens=60, requests=1),
    )
    critic.run.return_value = FakeRunResult(
        CriticOutput(passed=True, feedback="", confidence=0.95),
        usage=RunUsage(input_tokens=50, output_tokens=10, requests=1),
    )

    from herness.models.task import TaskRequest

    result = await orchestrator.run(TaskRequest(user_id="u1", input="介绍框架"))

    assert result.status == TaskStatus.COMPLETED
    assert result.usage.input_tokens == 430
    assert result.usage.output_tokens == 120
    assert result.usage.total_tokens == 550

    agent_messages = [
        msg for msg in result.messages if msg.role.value in {"supervisor", "worker", "critic"}
    ]
    assert all("usage" in msg.payload for msg in agent_messages)
