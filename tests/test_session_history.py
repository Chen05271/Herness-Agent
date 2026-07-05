"""会话历史与中台 get_session_history 测试。"""

from herness.middleware.session import SessionHistoryEntry, format_session_history
from herness.middleware.stub import InMemoryMiddleware
from herness.models.worker import WorkerOutput


async def test_get_session_history_empty() -> None:
    mw = InMemoryMiddleware()
    history = await mw.get_session_history("session_a")
    assert history == []


async def test_get_session_history_filters_by_session() -> None:
    mw = InMemoryMiddleware()
    await mw.write_task_result(
        "user_a",
        "task_1",
        WorkerOutput(content="第一次回答", summary="第一次"),
        metadata={"session_id": "session_a", "input": "你好", "final_answer": "你好！"},
    )
    await mw.write_task_result(
        "user_a",
        "task_2",
        WorkerOutput(content="其他会话", summary="其他"),
        metadata={"session_id": "session_b", "input": "别的", "final_answer": "别的"},
    )

    history = await mw.get_session_history("session_a", exclude_task_id="task_3", limit=5)
    assert len(history) == 1
    assert history[0].task_id == "task_1"
    assert history[0].input == "你好"
    assert history[0].answer == "你好！"


async def test_get_session_history_excludes_current_task() -> None:
    mw = InMemoryMiddleware()
    await mw.write_task_result(
        "user_a",
        "task_current",
        WorkerOutput(content="当前", summary="当前"),
        metadata={"session_id": "session_a", "input": "当前", "final_answer": "当前"},
    )

    history = await mw.get_session_history(
        "session_a",
        exclude_task_id="task_current",
        limit=5,
    )
    assert history == []


async def test_get_session_history_respects_limit_and_order() -> None:
    mw = InMemoryMiddleware()
    for index in range(3):
        await mw.write_task_result(
            "user_a",
            f"task_{index}",
            WorkerOutput(content=f"答 {index}", summary=f"摘要 {index}"),
            metadata={
                "session_id": "session_a",
                "input": f"问 {index}",
                "final_answer": f"答 {index}",
            },
        )

    history = await mw.get_session_history("session_a", limit=2)
    assert len(history) == 2
    assert history[0].input == "问 1"
    assert history[1].input == "问 2"


def test_format_session_history() -> None:
    text = format_session_history(
        [
            SessionHistoryEntry(task_id="t1", input="你好", answer="你好！"),
            SessionHistoryEntry(task_id="t2", input="继续", answer="好的"),
        ]
    )
    assert "会话历史" in text
    assert "你好" in text
    assert "继续" in text


def test_format_session_history_empty() -> None:
    assert "暂无历史" in format_session_history([])
