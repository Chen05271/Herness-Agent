"""任务生命周期与调度器状态模型 — 所有 Agent 间消息均经调度器流转。"""

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field

from herness.models.critic import CriticOutput
from herness.models.supervisor import SupervisorOutput
from herness.models.worker import WorkerOutput


class TaskStatus(StrEnum):
    """任务终态/运行态枚举。"""

    PENDING = "pending"       # 等待执行
    RUNNING = "running"       # 执行中
    COMPLETED = "completed"   # 成功完成
    FAILED = "failed"         # 失败
    TIMEOUT = "timeout"       # 超时
    ABORTED = "aborted"       # 被总管中止


class AgentRole(StrEnum):
    """消息来源角色 — 用于审计日志。"""

    SUPERVISOR = "supervisor"
    WORKER = "worker"
    CRITIC = "critic"
    ORCHESTRATOR = "orchestrator"


class TaskMessage(BaseModel):
    """审计日志条目 — 子 Agent 禁止直连，所有消息经调度器记录。"""

    id: str = Field(default_factory=lambda: str(uuid4()))
    role: AgentRole
    round_index: int
    content: str
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class TaskRequest(BaseModel):
    """用户发起的任务请求。"""

    user_id: str
    session_id: str = Field(default_factory=lambda: str(uuid4()))
    input: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class TaskResult(BaseModel):
    """调度器返回的最终结果。"""

    task_id: str
    status: TaskStatus
    answer: str = ""
    error: str = ""
    rounds_used: int = 0
    messages: list[TaskMessage] = Field(default_factory=list)


class TaskState(BaseModel):
    """单次任务运行的可变调度状态。"""

    task_id: str = Field(default_factory=lambda: str(uuid4()))
    request: TaskRequest
    status: TaskStatus = TaskStatus.PENDING
    round_index: int = 0
    messages: list[TaskMessage] = Field(default_factory=list)
    last_supervisor: SupervisorOutput | None = None
    last_worker: WorkerOutput | None = None
    last_critic: CriticOutput | None = None
    plan_hashes: list[str] = Field(default_factory=list)  # 用于检测循环规划
    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    finished_at: datetime | None = None


class OrchestratorConfig(BaseModel):
    """调度器运行参数（可从 Settings 映射而来）。"""

    max_rounds: int = 8
    step_timeout_seconds: float = 120.0
    task_timeout_seconds: float = 600.0
    max_retries_per_step: int = 2
