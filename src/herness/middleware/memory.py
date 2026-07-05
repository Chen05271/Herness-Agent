"""预合成全局记忆 — 由离线 Dreaming 管线生成，在线链路只读。"""

from datetime import datetime, timezone

from pydantic import BaseModel, Field


class SynthesizedMemorySlice(BaseModel):
    """记忆切片 — 按类别组织的事实/上下文片段。"""

    category: str = Field(description="类别，如 profile / facts / recent_context")
    content: str = Field(description="切片内容")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="置信度")
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="最后更新时间",
    )


class PreSynthesizedMemory(BaseModel):
    """预合成全局记忆包 — 任务启动时注入总管 Agent。"""

    user_id: str
    summary: str = Field(default="", description="高层用户/上下文摘要")
    slices: list[SynthesizedMemorySlice] = Field(default_factory=list)
    version: int = Field(default=1, description="版本号，离线管线刷新后递增")

    def to_prompt_block(self) -> str:
        """转为可注入 system prompt 的文本块。"""
        if not self.slices and not self.summary:
            return "（暂无预合成全局记忆）"

        lines = [f"## 全局记忆 (v{self.version})"]
        if self.summary:
            lines.append(f"摘要：{self.summary}")
        for slice_ in self.slices:
            lines.append(f"- [{slice_.category}] {slice_.content}")
        return "\n".join(lines)
