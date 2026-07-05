"""记忆增量合并 — 纯函数，便于单元测试。"""

from datetime import datetime, timezone

from herness.middleware.memory import PreSynthesizedMemory, SynthesizedMemorySlice
from herness.models.dreaming import DreamingOutput

MAX_SLICES = 30


def _slice_key(category: str, content: str) -> tuple[str, str]:
    return category.strip().lower(), content.strip()


def merge_memory(
    current: PreSynthesizedMemory,
    output: DreamingOutput,
    *,
    max_slices: int = MAX_SLICES,
) -> PreSynthesizedMemory:
    """将 Dreaming 输出合并进现有记忆，版本号 +1。"""
    merged: dict[tuple[str, str], SynthesizedMemorySlice] = {}
    now = datetime.now(timezone.utc)

    for slice_ in current.slices:
        key = _slice_key(slice_.category, slice_.content)
        merged[key] = slice_

    for item in output.new_slices:
        key = _slice_key(item.category, item.content)
        merged[key] = SynthesizedMemorySlice(
            category=item.category,
            content=item.content,
            confidence=item.confidence,
            updated_at=now,
        )

    slices = sorted(merged.values(), key=lambda s: s.updated_at, reverse=True)[:max_slices]

    return PreSynthesizedMemory(
        user_id=current.user_id,
        summary=output.updated_summary.strip() or current.summary,
        slices=slices,
        version=current.version + 1,
    )
