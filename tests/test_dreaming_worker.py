"""Dreaming Worker 单元测试 — mock 合成器，不依赖真实 LLM。"""

from dataclasses import dataclass

import pytest

from herness.config import Settings
from herness.dreaming.synthesizer import SynthesisResult
from herness.dreaming.worker import DreamingWorker
from herness.middleware.memory import PreSynthesizedMemory, SynthesizedMemorySlice
from herness.middleware.stub import InMemoryMiddleware
from herness.models.dreaming import NewBelief
from herness.models.task import TokenUsage
from herness.models.worker import WorkerOutput
from herness.observability.usage_recorder import bind_usage_store
from herness.observability.usage_store import InMemoryUsageStore


@dataclass
class FakeSynthesizer:
    """可注入的合成器，返回固定结果。"""

    result: SynthesisResult | None = None
    calls: int = 0

    async def synthesize(self, *, current, task_result, task_id) -> SynthesisResult:
        self.calls += 1
        assert self.result is not None
        return self.result


@pytest.fixture
def dreaming_settings() -> Settings:
    return Settings(dreaming_poll_timeout_seconds=1)


async def test_dreaming_worker_processes_job(dreaming_settings: Settings) -> None:
    mw = InMemoryMiddleware()
    user_id = "u1"
    task_id = "task-1"

    mw.seed_memory(user_id, "初始摘要", [SynthesizedMemorySlice(category="profile", content="中文")])
    await mw.write_task_result(
        user_id,
        task_id,
        WorkerOutput(content="用户说喜欢 Python", summary="记录偏好"),
    )
    await mw.enqueue_dreaming_job(user_id, task_id)

    synthesis = SynthesisResult(
        memory=PreSynthesizedMemory(
            user_id=user_id,
            summary="更新摘要",
            version=2,
            slices=[
                SynthesizedMemorySlice(category="profile", content="中文"),
                SynthesizedMemorySlice(category="preferences", content="喜欢 Python"),
            ],
        ),
        new_beliefs=[NewBelief(fact="用户喜欢 Python")],
        usage=TokenUsage(),
    )
    synthesizer = FakeSynthesizer(result=synthesis)
    worker = DreamingWorker(mw, synthesizer, dreaming_settings)  # type: ignore[arg-type]

    job = await mw.dequeue_dreaming_job()
    assert job == (user_id, task_id)

    await worker.process_job(user_id, task_id)

    memory = await mw.get_pre_synthesized_memory(user_id)
    assert memory.version == 2
    assert memory.summary == "更新摘要"
    assert len(memory.slices) == 2

    beliefs = await mw.query_beliefs(user_id, ["Python"])
    assert beliefs[0]["status"] == "supported"
    assert synthesizer.calls == 1


async def test_dreaming_worker_run_once_empty_queue(dreaming_settings: Settings) -> None:
    mw = InMemoryMiddleware()
    synthesizer = FakeSynthesizer(
        result=SynthesisResult(
            memory=PreSynthesizedMemory(user_id="u1"),
            new_beliefs=[],
            usage=TokenUsage(),
        )
    )
    worker = DreamingWorker(mw, synthesizer, dreaming_settings)  # type: ignore[arg-type]

    assert await worker.run_once() is False
    assert synthesizer.calls == 0


async def test_dreaming_worker_run_once_full_flow(dreaming_settings: Settings) -> None:
    mw = InMemoryMiddleware()
    user_id = "u2"
    task_id = "task-2"

    await mw.write_task_result(
        user_id,
        task_id,
        WorkerOutput(content="完成", summary="ok"),
    )
    await mw.enqueue_dreaming_job(user_id, task_id)

    synthesis = SynthesisResult(
        memory=PreSynthesizedMemory(user_id=user_id, summary="合成后", version=1),
        new_beliefs=[],
        usage=TokenUsage(),
    )
    synthesizer = FakeSynthesizer(result=synthesis)
    worker = DreamingWorker(mw, synthesizer, dreaming_settings)  # type: ignore[arg-type]

    assert await worker.run_once() is True
    memory = await mw.get_pre_synthesized_memory(user_id)
    assert memory.summary == "合成后"


async def test_dreaming_worker_retries_before_failure(dreaming_settings: Settings) -> None:
    mw = InMemoryMiddleware()
    user_id = "u1"
    task_id = "task-retry"

    await mw.write_task_result(
        user_id,
        task_id,
        WorkerOutput(content="完成", summary="ok"),
    )
    await mw.enqueue_dreaming_job(user_id, task_id)

    class FailingSynthesizer:
        def __init__(self) -> None:
            self.calls = 0

        async def synthesize(self, *, current, task_result, task_id) -> SynthesisResult:
            self.calls += 1
            raise RuntimeError("合成失败")

    settings = Settings(
        dreaming_poll_timeout_seconds=1,
        dreaming_max_retries=3,
        dreaming_retry_backoff_seconds=0.01,
    )
    synthesizer = FailingSynthesizer()
    worker = DreamingWorker(mw, synthesizer, settings)  # type: ignore[arg-type]

    with pytest.raises(RuntimeError, match="合成失败"):
        await worker.run_once()

    assert synthesizer.calls == 3


async def test_dreaming_worker_missing_task_result_raises(dreaming_settings: Settings) -> None:
    mw = InMemoryMiddleware()
    synthesis = SynthesisResult(
        memory=PreSynthesizedMemory(user_id="u1"),
        new_beliefs=[],
        usage=TokenUsage(),
    )
    worker = DreamingWorker(mw, FakeSynthesizer(result=synthesis), dreaming_settings)  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="任务结果不存在"):
        await worker.process_job("u1", "missing-task")


async def test_dreaming_worker_records_session_usage(dreaming_settings: Settings) -> None:
    store = InMemoryUsageStore()
    bind_usage_store(store, metrics_enabled=False)
    try:
        mw = InMemoryMiddleware()
        user_id = "u1"
        task_id = "task-usage"
        session_id = "consumer-u1:sess-dream"

        await mw.write_task_result(
            user_id,
            task_id,
            WorkerOutput(content="完成", summary="ok"),
            metadata={"session_id": session_id},
        )

        synthesis = SynthesisResult(
            memory=PreSynthesizedMemory(user_id=user_id, summary="合成后", version=1),
            new_beliefs=[],
            usage=TokenUsage(input_tokens=50, output_tokens=20, total_tokens=70, requests=1),
        )
        worker = DreamingWorker(mw, FakeSynthesizer(result=synthesis), dreaming_settings)  # type: ignore[arg-type]
        await worker.process_job(user_id, task_id)

        session_usage = await store.get_session_usage(user_id, session_id)
        assert session_usage.total_tokens == 70
    finally:
        bind_usage_store(None)
