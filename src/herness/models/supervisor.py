"""总管 Agent 结构化输出模型 — 锁定规划/委派/完成/中止四种动作。"""

from enum import StrEnum
from typing import Self

from pydantic import BaseModel, Field, model_validator

from herness.models.worker import WORKER_KINDS, WorkerKind


class SupervisorAction(StrEnum):
    """总管下一步动作枚举。"""

    DELEGATE = "delegate"   # 委派 Worker 执行
    COMPLETE = "complete"   # 任务完成，返回最终答案
    ABORT = "abort"         # 中止任务


class SupervisorOutput(BaseModel):
    """总管 Agent 的结构化输出，由 PydanticAI output_type 强制约束。"""

    action: SupervisorAction = Field(description="下一步调度动作")
    reasoning: str = Field(description="决策理由（简要）")
    task_instruction: str = Field(
        default="",
        description="单条委派指令（与 task_instructions 二选一，向后兼容）",
    )
    task_instructions: list[str] = Field(
        default_factory=list,
        description="多条并行委派指令（action=delegate 时至少一条）",
    )
    worker_types: list[WorkerKind] = Field(
        default_factory=list,
        description=(
            "与 task_instructions 对齐的 Worker 类型路由"
            "（default/research/code/summary/presentation/order_ops/product/traceability）"
        ),
    )
    final_answer: str = Field(
        default="",
        description="最终回复用户的内容（action=complete 时必填）",
    )
    abort_reason: str = Field(
        default="",
        description="中止原因（action=abort 时必填）",
    )

    @model_validator(mode="after")
    def sync_delegate_fields(self) -> Self:
        """单条 task_instruction 与 task_instructions 互相同步。"""
        if self.action != SupervisorAction.DELEGATE:
            return self

        if self.task_instructions and not self.task_instruction:
            if len(self.task_instructions) == 1:
                object.__setattr__(self, "task_instruction", self.task_instructions[0])
        elif self.task_instruction and not self.task_instructions:
            object.__setattr__(self, "task_instructions", [self.task_instruction])

        if self.task_instructions:
            default_kind: WorkerKind = "default"
            types = list(self.worker_types)
            if len(types) < len(self.task_instructions):
                types.extend([default_kind] * (len(self.task_instructions) - len(types)))
            elif len(types) > len(self.task_instructions):
                types = types[: len(self.task_instructions)]
            for wt in types:
                if wt not in WORKER_KINDS:
                    raise ValueError(f"未知 worker_type: {wt!r}，可选: {WORKER_KINDS}")
            object.__setattr__(self, "worker_types", types)

        return self

    @model_validator(mode="after")
    def validate_action_fields(self) -> Self:
        """各 action 必填字段校验。"""
        if self.action == SupervisorAction.DELEGATE:
            if not self.delegate_instructions():
                raise ValueError("delegate 动作需要 task_instruction 或 task_instructions")
        elif self.action == SupervisorAction.COMPLETE:
            if not self.final_answer.strip():
                raise ValueError("complete 动作需要 final_answer")
        elif self.action == SupervisorAction.ABORT:
            if not self.abort_reason.strip():
                raise ValueError("abort 动作需要 abort_reason")
        return self

    def delegate_instructions(self) -> list[str]:
        """返回规范化后的委派指令列表。"""
        return list(self.task_instructions)

    def delegate_worker_types(self) -> list[WorkerKind]:
        """返回与指令对齐的 Worker 类型列表。"""
        instructions = self.delegate_instructions()
        if not instructions:
            return []
        if self.worker_types:
            return list(self.worker_types)
        return ["default"] * len(instructions)
