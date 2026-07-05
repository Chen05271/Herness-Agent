"""Dreaming 离线记忆合成 — 结构化输出模型。"""

from pydantic import BaseModel, Field


class DreamingSlice(BaseModel):
    """待合并的新记忆切片。"""

    category: str = Field(description="类别，如 profile / facts / preferences / recent_context")
    content: str = Field(description="切片内容")
    confidence: float = Field(default=0.8, ge=0.0, le=1.0)


class NewBelief(BaseModel):
    """从任务结果提炼的可验证事实。"""

    fact: str = Field(description="可写入信念库的事实陈述")
    confidence: float = Field(default=0.8, ge=0.0, le=1.0)


class DreamingOutput(BaseModel):
    """Dreaming LLM 合成结果 — 增量更新现有记忆。"""

    updated_summary: str = Field(description="合并后的用户/上下文高层摘要")
    new_slices: list[DreamingSlice] = Field(
        default_factory=list,
        description="新增或更新的记忆切片",
    )
    new_beliefs: list[NewBelief] = Field(
        default_factory=list,
        description="从任务结果提炼的可验证事实",
    )
    merge_notes: str = Field(default="", description="合成说明（可选，不写入记忆）")
