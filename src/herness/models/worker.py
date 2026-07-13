"""执行 Agent 结构化输出模型 — Worker 仅负责完成任务，不可见全局记忆。"""

from typing import Literal

from pydantic import BaseModel, Field

WorkerKind = Literal[
    "default",
    "research",
    "code",
    "summary",
    "presentation",
    "order_ops",
    "product",
    "traceability",
]

WORKER_KINDS: tuple[WorkerKind, ...] = (
    "default",
    "research",
    "code",
    "summary",
    "presentation",
    "order_ops",
    "product",
    "traceability",
)


class WorkerToolInvocation(BaseModel):
    """Worker 单次工具调用记录（由调度器从 Agent 消息历史提取）。"""

    tool_name: str = Field(description="工具名称")
    result: str = Field(description="工具返回文本")
    error: bool = Field(default=False, description="返回是否表示失败")


class WorkerOutput(BaseModel):
    """执行 Agent 的结构化输出。"""

    content: str = Field(description="主要执行结果或回答")
    summary: str = Field(description="一行摘要，说明做了什么")
    artifacts: list[str] = Field(
        default_factory=list,
        description="可选产物引用（文件路径、ID 等）",
    )
    needs_verification: bool = Field(
        default=True,
        description="是否需要 Critic 校验",
    )
    tool_invocations: list[WorkerToolInvocation] = Field(
        default_factory=list,
        description="本步工具调用记录，供 Critic 校验",
    )
