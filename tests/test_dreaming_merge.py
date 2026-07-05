"""Dreaming 记忆合并单元测试。"""

from datetime import datetime, timezone

from herness.dreaming.merge import merge_memory
from herness.middleware.memory import PreSynthesizedMemory, SynthesizedMemorySlice
from herness.models.dreaming import DreamingOutput, DreamingSlice, NewBelief


def test_merge_memory_increments_version() -> None:
    current = PreSynthesizedMemory(
        user_id="u1",
        summary="旧摘要",
        version=2,
        slices=[SynthesizedMemorySlice(category="profile", content="语言：中文")],
    )
    output = DreamingOutput(
        updated_summary="新摘要",
        new_slices=[DreamingSlice(category="facts", content="偏好简洁回答")],
        new_beliefs=[NewBelief(fact="用户偏好简洁")],
    )

    merged = merge_memory(current, output)
    assert merged.version == 3
    assert merged.summary == "新摘要"
    assert len(merged.slices) == 2
    categories = {s.category for s in merged.slices}
    assert categories == {"profile", "facts"}


def test_merge_memory_deduplicates_slices() -> None:
    now = datetime.now(timezone.utc)
    current = PreSynthesizedMemory(
        user_id="u1",
        summary="摘要",
        slices=[SynthesizedMemorySlice(category="facts", content="重复事实", updated_at=now)],
    )
    output = DreamingOutput(
        updated_summary="摘要",
        new_slices=[DreamingSlice(category="facts", content="重复事实")],
    )

    merged = merge_memory(current, output)
    assert len(merged.slices) == 1


def test_merge_memory_keeps_summary_when_empty() -> None:
    current = PreSynthesizedMemory(user_id="u1", summary="保留摘要", version=1)
    output = DreamingOutput(updated_summary="   ", new_slices=[])

    merged = merge_memory(current, output)
    assert merged.summary == "保留摘要"
    assert merged.version == 2
