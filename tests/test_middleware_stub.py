"""InMemoryMiddleware 单元测试。"""

import pytest

from herness.middleware.memory import SynthesizedMemorySlice
from herness.middleware.stub import InMemoryMiddleware
from herness.models.worker import WorkerOutput


@pytest.fixture
def mw() -> InMemoryMiddleware:
    return InMemoryMiddleware()


async def test_get_pre_synthesized_memory_default(mw: InMemoryMiddleware) -> None:
    memory = await mw.get_pre_synthesized_memory("user_a")
    assert memory.user_id == "user_a"
    assert "尚未生成记忆" in memory.summary


async def test_seed_memory(mw: InMemoryMiddleware) -> None:
    mw.seed_memory("user_a", "测试摘要", [SynthesizedMemorySlice(category="facts", content="x")])
    memory = await mw.get_pre_synthesized_memory("user_a")
    assert memory.summary == "测试摘要"
    assert len(memory.slices) == 1


async def test_get_task_context_no_global_memory(mw: InMemoryMiddleware) -> None:
    ctx = await mw.get_task_context("user_a", "task_1")
    assert ctx["user_id"] == "user_a"
    assert ctx["task_id"] == "task_1"
    assert "note" in ctx


async def test_query_beliefs_supported_and_unknown(mw: InMemoryMiddleware) -> None:
    mw.seed_belief("user_a", "Herness Agent 是多 Agent 框架")
    results = await mw.query_beliefs("user_a", ["Herness Agent", "不存在的声明"])
    assert results[0]["status"] == "supported"
    assert results[1]["status"] == "unknown"


async def test_write_task_result_and_dreaming_queue(mw: InMemoryMiddleware) -> None:
    output = WorkerOutput(content="结果", summary="完成")
    await mw.write_task_result("user_a", "task_1", output)
    await mw.enqueue_dreaming_job("user_a", "task_1")
    assert mw._task_results["task_1"].content == "结果"
    assert mw.dreaming_queue == [("user_a", "task_1")]
