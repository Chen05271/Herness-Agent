"""PreSynthesizedMemory 单元测试。"""

from herness.middleware.memory import PreSynthesizedMemory, SynthesizedMemorySlice


def test_to_prompt_block_empty() -> None:
    memory = PreSynthesizedMemory(user_id="u1")
    assert "暂无预合成全局记忆" in memory.to_prompt_block()


def test_to_prompt_block_with_content() -> None:
    memory = PreSynthesizedMemory(
        user_id="u1",
        summary="偏好简洁",
        version=2,
        slices=[
            SynthesizedMemorySlice(category="profile", content="语言：中文"),
            SynthesizedMemorySlice(category="facts", content="项目：Herness"),
        ],
    )
    block = memory.to_prompt_block()
    assert "全局记忆 (v2)" in block
    assert "偏好简洁" in block
    assert "[profile] 语言：中文" in block
    assert "[facts] 项目：Herness" in block
