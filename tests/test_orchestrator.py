"""调度器主流程测试 — mock Agent，覆盖各终态。"""

from unittest.mock import MagicMock


from herness.models.critic import CriticOutput
from herness.models.supervisor import SupervisorAction, SupervisorOutput
from herness.models.task import TaskRequest, TaskStatus
from herness.middleware.stub import InMemoryMiddleware
from herness.models.worker import WorkerOutput
from herness.observability.metrics import reset_metrics_registry
from herness.orchestrator.scheduler import Orchestrator
from tests.conftest import FakeRunResult


async def test_complete_flow_with_verification(
    orchestrator: Orchestrator,
    mock_agents: tuple[MagicMock, MagicMock, MagicMock],
) -> None:
    """delegate → worker → critic pass → supervisor complete。"""
    supervisor, worker, critic = mock_agents

    supervisor.run.side_effect = [
        FakeRunResult(
            SupervisorOutput(
                action=SupervisorAction.DELEGATE,
                reasoning="需要执行",
                task_instruction="写一段介绍",
            )
        ),
        FakeRunResult(
            SupervisorOutput(
                action=SupervisorAction.COMPLETE,
                reasoning="校验通过",
                final_answer="Herness 是一个多 Agent 框架。",
            )
        ),
    ]
    worker.run.return_value = FakeRunResult(
        WorkerOutput(content="框架介绍内容", summary="已撰写介绍", needs_verification=True)
    )
    critic.run.return_value = FakeRunResult(
        CriticOutput(passed=True, feedback="", confidence=0.95)
    )

    result = await orchestrator.run(TaskRequest(user_id="u1", input="介绍框架"))

    assert result.status == TaskStatus.COMPLETED
    assert result.answer == "Herness 是一个多 Agent 框架。"
    assert result.rounds_used == 2
    assert supervisor.run.call_count == 2
    assert worker.run.call_count == 1
    assert critic.run.call_count == 1


async def test_skip_critic_when_no_verification_needed(
    orchestrator: Orchestrator,
    mock_agents: tuple[MagicMock, MagicMock, MagicMock],
) -> None:
    """needs_verification=false 时跳过 Critic。"""
    supervisor, worker, critic = mock_agents

    supervisor.run.side_effect = [
        FakeRunResult(
            SupervisorOutput(
                action=SupervisorAction.DELEGATE,
                reasoning="简单任务",
                task_instruction="回复 OK",
            )
        ),
        FakeRunResult(
            SupervisorOutput(
                action=SupervisorAction.COMPLETE,
                reasoning="完成",
                final_answer="OK",
            )
        ),
    ]
    worker.run.return_value = FakeRunResult(
        WorkerOutput(content="OK", summary="已回复", needs_verification=False)
    )

    result = await orchestrator.run(TaskRequest(user_id="u1", input="说 OK"))

    assert result.status == TaskStatus.COMPLETED
    assert critic.run.call_count == 0


async def test_supervisor_abort(
    orchestrator: Orchestrator,
    mock_agents: tuple[MagicMock, MagicMock, MagicMock],
) -> None:
    supervisor, _, _ = mock_agents
    supervisor.run.return_value = FakeRunResult(
        SupervisorOutput(
            action=SupervisorAction.ABORT,
            reasoning="无法处理",
            abort_reason="输入不合法",
        )
    )

    result = await orchestrator.run(TaskRequest(user_id="u1", input="bad"))

    assert result.status == TaskStatus.ABORTED
    assert result.error == "输入不合法"


async def test_critic_rejection_retries_supervisor(
    orchestrator: Orchestrator,
    mock_agents: tuple[MagicMock, MagicMock, MagicMock],
) -> None:
    """Critic 驳回后 Supervisor 收到反馈并重试。"""
    supervisor, worker, critic = mock_agents

    supervisor.run.side_effect = [
        FakeRunResult(
            SupervisorOutput(
                action=SupervisorAction.DELEGATE,
                reasoning="首次委派",
                task_instruction="写介绍",
            )
        ),
        FakeRunResult(
            SupervisorOutput(
                action=SupervisorAction.DELEGATE,
                reasoning="修正后重试",
                task_instruction="写更准确的介绍",
            )
        ),
        FakeRunResult(
            SupervisorOutput(
                action=SupervisorAction.COMPLETE,
                reasoning="完成",
                final_answer="最终答案",
            )
        ),
    ]
    worker.run.return_value = FakeRunResult(
        WorkerOutput(content="内容", summary="摘要", needs_verification=True)
    )
    critic.run.side_effect = [
        FakeRunResult(CriticOutput(passed=False, feedback="事实有误")),
        FakeRunResult(CriticOutput(passed=True, feedback="")),
    ]

    result = await orchestrator.run(TaskRequest(user_id="u1", input="介绍"))

    assert result.status == TaskStatus.COMPLETED
    assert supervisor.run.call_count == 3
    # 第二次 Supervisor 调用应包含 Critic 反馈
    second_prompt = supervisor.run.call_args_list[1].args[0]
    assert "[Critic 反馈]" in second_prompt
    assert "事实有误" in second_prompt


async def test_persist_writes_to_middleware(
    orchestrator: Orchestrator,
    mock_agents: tuple[MagicMock, MagicMock, MagicMock],
    middleware,
) -> None:
    supervisor, worker, _ = mock_agents

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
                final_answer="done",
            )
        ),
    ]
    worker.run.return_value = FakeRunResult(
        WorkerOutput(content="x", summary="y", needs_verification=False)
    )

    result = await orchestrator.run(TaskRequest(user_id="u1", input="test"))

    assert result.status == TaskStatus.COMPLETED
    assert len(middleware.dreaming_queue) == 1
    assert middleware.dreaming_queue[0] == ("u1", result.task_id)


async def test_orchestrator_records_metrics(
    middleware: InMemoryMiddleware,
    test_settings,
    test_config,
    mock_agents: tuple[MagicMock, MagicMock, MagicMock],
) -> None:
    """任务完成与 Critic 驳回应写入指标。"""
    metrics = reset_metrics_registry()
    supervisor, worker, critic = mock_agents

    supervisor.run.side_effect = [
        FakeRunResult(
            SupervisorOutput(
                action=SupervisorAction.DELEGATE,
                reasoning="委派",
                task_instruction="写内容",
            )
        ),
        FakeRunResult(
            SupervisorOutput(
                action=SupervisorAction.COMPLETE,
                reasoning="完成",
                final_answer="OK",
            )
        ),
    ]
    worker.run.return_value = FakeRunResult(
        WorkerOutput(content="内容", summary="摘要", needs_verification=True)
    )
    critic.run.side_effect = [
        FakeRunResult(CriticOutput(passed=False, feedback="驳回")),
        FakeRunResult(CriticOutput(passed=True, feedback="")),
    ]

    orchestrator = Orchestrator(
        middleware=middleware,
        settings=test_settings,
        config=test_config,
        supervisor=supervisor,
        worker=worker,
        critic=critic,
        metrics=metrics,
    )
    result = await orchestrator.run(TaskRequest(user_id="u1", input="test"))

    assert result.status == TaskStatus.COMPLETED
    snapshot = metrics.snapshot()
    assert snapshot["tasks_total"]["completed"] == 1
    assert snapshot["critic_rejections_total"] == 1
