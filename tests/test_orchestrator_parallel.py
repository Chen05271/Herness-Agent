"""并行 Worker 调度测试 — P3-1 多指令 dispatch 与 Critic 批量校验。"""

from unittest.mock import MagicMock

import pytest

from herness.models.critic import CriticOutput
from herness.models.supervisor import SupervisorAction, SupervisorOutput
from herness.models.task import TaskRequest, TaskStatus
from herness.models.worker import WorkerOutput
from herness.orchestrator.scheduler import Orchestrator
from tests.conftest import FakeRunResult


async def test_parallel_workers_all_pass(
    orchestrator: Orchestrator,
    mock_agents: tuple[MagicMock, MagicMock, MagicMock],
) -> None:
    """多条 task_instructions 并行执行，Critic 全部通过后完成。"""
    supervisor, worker, critic = mock_agents

    supervisor.run.side_effect = [
        FakeRunResult(
            SupervisorOutput(
                action=SupervisorAction.DELEGATE,
                reasoning="并行调研与摘要",
                task_instructions=["调研背景", "写摘要"],
                worker_types=["research", "summary"],
            )
        ),
        FakeRunResult(
            SupervisorOutput(
                action=SupervisorAction.COMPLETE,
                reasoning="汇总完成",
                final_answer="综合结果",
            )
        ),
    ]
    worker.run.side_effect = [
        FakeRunResult(
            WorkerOutput(content="调研内容", summary="调研完成", needs_verification=True)
        ),
        FakeRunResult(
            WorkerOutput(content="摘要内容", summary="摘要完成", needs_verification=True)
        ),
    ]
    critic.run.side_effect = [
        FakeRunResult(CriticOutput(passed=True, feedback="", confidence=0.9)),
        FakeRunResult(CriticOutput(passed=True, feedback="", confidence=0.9)),
    ]

    result = await orchestrator.run(TaskRequest(user_id="u1", input="并行任务"))

    assert result.status == TaskStatus.COMPLETED
    assert result.answer == "综合结果"
    assert worker.run.call_count == 2
    assert critic.run.call_count == 2


async def test_parallel_workers_partial_critic_rejection(
    orchestrator: Orchestrator,
    mock_agents: tuple[MagicMock, MagicMock, MagicMock],
) -> None:
    """并行 Worker 中部分 Critic 驳回，总管收到合并反馈。"""
    supervisor, worker, critic = mock_agents

    supervisor.run.side_effect = [
        FakeRunResult(
            SupervisorOutput(
                action=SupervisorAction.DELEGATE,
                reasoning="并行",
                task_instructions=["任务A", "任务B"],
            )
        ),
        FakeRunResult(
            SupervisorOutput(
                action=SupervisorAction.COMPLETE,
                reasoning="修正后完成",
                final_answer="OK",
            )
        ),
    ]
    worker.run.return_value = FakeRunResult(
        WorkerOutput(content="x", summary="y", needs_verification=True)
    )
    critic.run.side_effect = [
        FakeRunResult(CriticOutput(passed=False, feedback="A 有误")),
        FakeRunResult(CriticOutput(passed=True, feedback="")),
    ]

    result = await orchestrator.run(TaskRequest(user_id="u1", input="test"))

    assert result.status == TaskStatus.COMPLETED
    second_prompt = supervisor.run.call_args_list[1].args[0]
    assert "A 有误" in second_prompt


async def test_single_task_instruction_backward_compat(
    orchestrator: Orchestrator,
    mock_agents: tuple[MagicMock, MagicMock, MagicMock],
) -> None:
    """单条 task_instruction 仍走原有路径。"""
    supervisor, worker, critic = mock_agents

    supervisor.run.side_effect = [
        FakeRunResult(
            SupervisorOutput(
                action=SupervisorAction.DELEGATE,
                reasoning="单条",
                task_instruction="只做一件事",
            )
        ),
        FakeRunResult(
            SupervisorOutput(
                action=SupervisorAction.COMPLETE,
                reasoning="完成",
                final_answer="done",
            )
        ),
    ]
    worker.run.return_value = FakeRunResult(
        WorkerOutput(content="x", summary="y", needs_verification=False)
    )

    result = await orchestrator.run(TaskRequest(user_id="u1", input="单条"))

    assert result.status == TaskStatus.COMPLETED
    assert worker.run.call_count == 1


async def test_supervisor_output_syncs_instructions() -> None:
    """task_instruction 与 task_instructions 自动互相同步。"""
    out = SupervisorOutput(
        action=SupervisorAction.DELEGATE,
        reasoning="test",
        task_instruction="单条指令",
    )
    assert out.task_instructions == ["单条指令"]
    assert out.delegate_worker_types() == ["default"]

    multi = SupervisorOutput(
        action=SupervisorAction.DELEGATE,
        reasoning="test",
        task_instructions=["a", "b"],
        worker_types=["code"],
    )
    assert multi.worker_types == ["code", "default"]
    assert multi.delegate_instructions() == ["a", "b"]


async def test_delegate_without_instructions_fails(
    orchestrator: Orchestrator,
    mock_agents: tuple[MagicMock, MagicMock, MagicMock],
) -> None:
    supervisor, _, _ = mock_agents
    supervisor.run.return_value = FakeRunResult(
        SupervisorOutput(
            action=SupervisorAction.DELEGATE,
            reasoning="空指令",
        )
    )

    result = await orchestrator.run(TaskRequest(user_id="u1", input="bad"))

    assert result.status == TaskStatus.FAILED
    assert "task_instruction" in result.error
