"""总管 Agent 结构化输出模型 — 锁定规划/委派/完成/中止四种动作。"""

from enum import StrEnum

from pydantic import BaseModel, Field


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
        description="委派 Worker 时的任务指令（action=delegate 时必填）",
    )
    final_answer: str = Field(
        default="",
        description="最终回复用户的内容（action=complete 时必填）",
    )
    abort_reason: str = Field(
        default="",
        description="中止原因（action=abort 时必填）",
    )
