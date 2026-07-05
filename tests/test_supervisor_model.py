"""SupervisorOutput 模型校验测试。"""

import pytest

from herness.models.supervisor import SupervisorAction, SupervisorOutput


def test_delegate_requires_instruction() -> None:
    with pytest.raises(ValueError, match="delegate"):
        SupervisorOutput(action=SupervisorAction.DELEGATE, reasoning="无指令")


def test_complete_requires_final_answer() -> None:
    with pytest.raises(ValueError, match="final_answer"):
        SupervisorOutput(action=SupervisorAction.COMPLETE, reasoning="无答案")


def test_abort_requires_reason() -> None:
    with pytest.raises(ValueError, match="abort_reason"):
        SupervisorOutput(action=SupervisorAction.ABORT, reasoning="无理由")


def test_valid_outputs() -> None:
    SupervisorOutput(
        action=SupervisorAction.DELEGATE,
        reasoning="执行",
        task_instruction="做某事",
    )
    SupervisorOutput(
        action=SupervisorAction.COMPLETE,
        reasoning="完成",
        final_answer="结果",
    )
    SupervisorOutput(
        action=SupervisorAction.ABORT,
        reasoning="中止",
        abort_reason="无法完成",
    )
