"""校验 Agent 结构化输出模型 — Schema 校验 + Hereness 事实一致性检查。"""

from pydantic import BaseModel, Field


class FactCheckItem(BaseModel):
    """单条事实核查结果。"""

    claim: str = Field(description="待核查的声明")
    status: str = Field(description="核查状态：supported | contradicted | unknown")
    evidence: str = Field(default="", description="支持或反驳的证据")


class CriticOutput(BaseModel):
    """校验 Agent 的结构化输出。"""

    passed: bool = Field(description="Worker 输出是否通过校验")
    schema_valid: bool = Field(default=True, description="结构是否合法")
    feedback: str = Field(
        default="",
        description="校验失败时的可执行反馈（供总管重试参考）",
    )
    fact_checks: list[FactCheckItem] = Field(
        default_factory=list,
        description="逐条事实核查明细",
    )
    confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="校验置信度")
