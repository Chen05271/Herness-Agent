"""调度器 Hereness 后校验集成测试 — 不依赖真实 LLM。"""

from unittest.mock import MagicMock

import pytest

from herness.config import Settings
from herness.middleware.stub import InMemoryMiddleware
from herness.models.critic import CriticOutput, FactCheckItem
from herness.models.supervisor import SupervisorAction, SupervisorOutput
from herness.models.task import OrchestratorConfig, TaskRequest, TaskStatus
from herness.models.worker import WorkerOutput
from herness.orchestrator.scheduler import Orchestrator
from tests.conftest import FakeRunResult


@pytest.fixture
def hereness_orchestrator(
    mock_agents: tuple[MagicMock, MagicMock, MagicMock],
) -> Orchestrator:
    middleware = InMemoryMiddleware(hereness_enabled=True)
    middleware.seed_belief("u1", "用户不喜欢 Python", source="manual")
    settings = Settings(
        max_rounds=5,
        step_timeout_seconds=5.0,
        task_timeout_seconds=30.0,
        max_retries_per_step=2,
        hereness_enabled=True,
    )
    config = OrchestratorConfig(
        max_rounds=settings.max_rounds,
        step_timeout_seconds=settings.step_timeout_seconds,
        task_timeout_seconds=settings.task_timeout_seconds,
        max_retries_per_step=settings.max_retries_per_step,
        max_parallel_workers=settings.max_parallel_workers,
    )
    supervisor, worker, critic = mock_agents
    return Orchestrator(
        middleware=middleware,
        settings=settings,
        config=config,
        supervisor=supervisor,
        worker=worker,
        critic=critic,
    )


async def test_orchestrator_hereness_rejects_when_critic_skips_contradiction(
    hereness_orchestrator: Orchestrator,
    mock_agents: tuple[MagicMock, MagicMock, MagicMock],
) -> None:
    """Critic LLM 漏检矛盾时，后校验应驳回并将反馈注入下一轮 Supervisor。"""
    supervisor, worker, critic = mock_agents

    supervisor.run.side_effect = [
        FakeRunResult(
            SupervisorOutput(
                action=SupervisorAction.DELEGATE,
                reasoning="需要执行",
                task_instruction="介绍 Python 偏好",
            )
        ),
        FakeRunResult(
            SupervisorOutput(
                action=SupervisorAction.DELEGATE,
                reasoning="修正后重试",
                task_instruction="修正 Python 相关表述",
            )
        ),
        FakeRunResult(
            SupervisorOutput(
                action=SupervisorAction.COMPLETE,
                reasoning="重试后完成",
                final_answer="已修正输出。",
            )
        ),
    ]
    worker.run.side_effect = [
        FakeRunResult(
            WorkerOutput(
                content="用户喜欢 Python 编程。",
                summary="Python 偏好",
                needs_verification=True,
            )
        ),
        FakeRunResult(
            WorkerOutput(
                content="用户不使用 Python。",
                summary="已修正",
                needs_verification=True,
            )
        ),
    ]
    critic.run.side_effect = [
        FakeRunResult(CriticOutput(passed=True, fact_checks=[], confidence=0.95)),
        FakeRunResult(CriticOutput(passed=True, fact_checks=[], confidence=0.9)),
    ]

    result = await hereness_orchestrator.run(
        TaskRequest(user_id="u1", input="介绍 Python 偏好")
    )

    assert result.status == TaskStatus.COMPLETED
    assert critic.run.call_count == 2
    assert worker.run.call_count == 2
    retry_prompt = supervisor.run.call_args_list[1][0][0]
    assert "Critic 反馈" in retry_prompt
    assert "矛盾" in retry_prompt


async def test_orchestrator_hereness_rejects_partial_fact_checks(
    hereness_orchestrator: Orchestrator,
    mock_agents: tuple[MagicMock, MagicMock, MagicMock],
) -> None:
    """Critic 只核查安全声明时，后校验仍应发现正文中的矛盾。"""
    supervisor, worker, critic = mock_agents

    supervisor.run.side_effect = [
        FakeRunResult(
            SupervisorOutput(
                action=SupervisorAction.DELEGATE,
                reasoning="执行",
                task_instruction="写介绍",
            )
        ),
        FakeRunResult(
            SupervisorOutput(
                action=SupervisorAction.ABORT,
                reasoning="无法修正",
                abort_reason="信念库矛盾无法消除",
            )
        ),
    ]
    worker.run.return_value = FakeRunResult(
        WorkerOutput(
            content="Herness 是多 Agent 框架。用户喜欢 Python。",
            summary="介绍",
            needs_verification=True,
        )
    )
    critic.run.return_value = FakeRunResult(
        CriticOutput(
            passed=True,
            fact_checks=[
                FactCheckItem(
                    claim="Herness 是多 Agent 框架",
                    status="unknown",
                    evidence="",
                )
            ],
            confidence=0.95,
        )
    )

    result = await hereness_orchestrator.run(TaskRequest(user_id="u1", input="写介绍"))

    assert result.status == TaskStatus.ABORTED
    assert critic.run.call_count == 1
    assert worker.run.call_count == 1
    retry_prompt = supervisor.run.call_args_list[1][0][0]
    assert "Critic 反馈" in retry_prompt
    assert "Python" in retry_prompt
