"""执行 Agent 结构化输出模型 — Worker 仅负责完成任务，不可见全局记忆。"""

from typing import Literal

from pydantic import BaseModel, Field

WorkerKind = Literal["default", "research", "code", "summary"]

WORKER_KINDS: tuple[WorkerKind, ...] = ("default", "research", "code", "summary")


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
