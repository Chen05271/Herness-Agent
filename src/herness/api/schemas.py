"""API 请求/响应模型。"""

from datetime import datetime

from pydantic import BaseModel, Field

from herness.models.task import TaskMessage, TaskRequest, TaskStatus, TokenUsage


class TaskSubmitResponse(BaseModel):
    """POST /v1/tasks 响应。"""

    task_id: str
    status: TaskStatus
    created_at: datetime


class TaskStatusResponse(BaseModel):
    """GET /v1/tasks/{id} 响应。"""

    task_id: str
    status: TaskStatus
    answer: str = ""
    error: str = ""
    rounds_used: int = 0
    usage: TokenUsage = Field(default_factory=TokenUsage)
    created_at: datetime
    updated_at: datetime


class TaskMessagesResponse(BaseModel):
    """GET /v1/tasks/{id}/messages 响应。"""

    task_id: str
    messages: list[TaskMessage] = Field(default_factory=list)


class TaskCancelResponse(BaseModel):
    """DELETE /v1/tasks/{id} 响应。"""

    task_id: str
    status: TaskStatus


class SessionUsageResponse(BaseModel):
    """GET /v1/sessions/{id}/usage 响应。"""

    user_id: str
    session_id: str
    usage: TokenUsage = Field(default_factory=TokenUsage)


class UserUsageResponse(BaseModel):
    """GET /v1/users/{id}/usage 响应。"""

    user_id: str
    usage: TokenUsage = Field(default_factory=TokenUsage)


class PublicConfigFeatures(BaseModel):
    """公开能力开关（不含敏感配置）。"""

    rag_enabled: bool = False
    dreaming_enabled: bool = False
    hereness_enabled: bool = False
    agri_commerce_enabled: bool = False
    otel_enabled: bool = False
    skills_enabled: bool = False
    ppt_enabled: bool = False


class PublicSkillInfo(BaseModel):
    """公开 Skill 元信息。"""

    name: str
    description: str = ""
    worker_kind: str = "default"


class PublicConfigLimits(BaseModel):
    """公开 token 配额上限；0 表示不限。"""

    token_budget_per_user: int = 0
    token_budget_per_session: int = 0


class PublicConfigResponse(BaseModel):
    """GET /v1/config/public 响应。"""

    llm_model: str = ""
    api_version: str = "0.1.0"
    features: PublicConfigFeatures = Field(default_factory=PublicConfigFeatures)
    limits: PublicConfigLimits = Field(default_factory=PublicConfigLimits)
    skills: list[PublicSkillInfo] = Field(default_factory=list)


class RagIngestRequest(BaseModel):
    """POST /v1/rag/ingest 请求。"""

    collection_id: str = "default"
    collection_name: str = ""
    text: str
    source: str = "api"
    persona: str | None = None
    build_communities: bool = False
    user_id: str = ""


class RagIngestResponse(BaseModel):
    chunk_ids: list[int]
    collection_id: str
    communities_built: int = 0


class RagSearchRequest(BaseModel):
    """POST /v1/rag/search 请求。"""

    query: str
    collection_id: str = "default"
    user_id: str = ""


class RagHitResponse(BaseModel):
    chunk_id: int
    content: str
    score: float
    source: str = ""
    retrieval_channel: str = ""


class RagSearchResponse(BaseModel):
    query: str
    collection_id: str
    hits: list[RagHitResponse]
    coarse_count: int = 0
    fine_count: int = 0


class RagGraphEntityResponse(BaseModel):
    name: str
    entity_type: str = "concept"
    chunk_ids: list[int] = Field(default_factory=list)


class RagGraphEdgeResponse(BaseModel):
    source: str
    target: str
    relation: str = "related_to"
    chunk_id: int | None = None


class RagGraphCommunityResponse(BaseModel):
    community_id: str
    summary: str
    entity_names: list[str] = Field(default_factory=list)


class RagGraphResponse(BaseModel):
    collection_id: str
    entities: list[RagGraphEntityResponse]
    edges: list[RagGraphEdgeResponse]
    communities: list[RagGraphCommunityResponse]
    entity_count: int = 0
    edge_count: int = 0
    community_count: int = 0


# 复用现有 TaskRequest 作为 POST body
TaskCreateRequest = TaskRequest
