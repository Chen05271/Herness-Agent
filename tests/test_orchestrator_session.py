"""调度器会话多轮集成测试。"""

from unittest.mock import MagicMock

from herness.models.supervisor import SupervisorAction, SupervisorOutput
from herness.models.task import TaskRequest, TaskStatus
from herness.models.worker import WorkerOutput
from herness.orchestrator.scheduler import Orchestrator
from tests.conftest import FakeRunResult


async def test_supervisor_receives_session_history(
    orchestrator: Orchestrator,
    middleware,
    mock_agents: tuple[MagicMock, MagicMock, MagicMock],
) -> None:
    """同 session 第二次任务应加载前序历史并注入 Supervisor deps。"""
    supervisor, worker, critic = mock_agents
    session_id = "session_multi"

    await middleware.write_task_result(
        "u1",
        "task_prev",
        WorkerOutput(content="上次回答", summary="上次"),
        metadata={
            "session_id": session_id,
            "input": "上次问题",
            "final_answer": "上次回答内容",
        },
    )

    supervisor.run.return_value = FakeRunResult(
        SupervisorOutput(
            action=SupervisorAction.COMPLETE,
            reasoning="直接完成",
            final_answer="收到",
        )
    )

    await orchestrator.run(
        TaskRequest(user_id="u1", session_id=session_id, input="接着聊")
    )

    deps = supervisor.run.call_args.kwargs["deps"]
    assert len(deps.session_history) == 1
    assert deps.session_history[0].input == "上次问题"
    assert deps.session_history[0].answer == "上次回答内容"
    assert deps.session_id == session_id


async def test_complete_writes_session_record(
    orchestrator: Orchestrator,
    middleware,
    mock_agents: tuple[MagicMock, MagicMock, MagicMock],
) -> None:
    """任务完成时应写入带 session 元数据的 task_result。"""
    supervisor, _, _ = mock_agents
    session_id = "session_write"

    supervisor.run.return_value = FakeRunResult(
        SupervisorOutput(
            action=SupervisorAction.COMPLETE,
            reasoning="完成",
            final_answer="最终答复",
        )
    )

    result = await orchestrator.run(
        TaskRequest(user_id="u1", session_id=session_id, input="问题")
    )

    assert result.status == TaskStatus.COMPLETED
    history = await middleware.get_session_history(session_id, limit=5)
    assert len(history) == 1
    assert history[0].input == "问题"
    assert history[0].answer == "最终答复"
