"""Token 用量来源枚举。"""

from enum import StrEnum


class UsageSource(StrEnum):
    """LLM / Embedding 用量来源。"""

    ORCHESTRATOR = "orchestrator"
    DREAMING = "dreaming"
    EMBEDDING = "embedding"
    RAG = "rag"
