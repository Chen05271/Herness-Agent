"""API 请求/响应模型。"""

from datetime import datetime

from pydantic import BaseModel, Field

from herness.models.task import TaskMessage, TaskRequest, TaskStatus


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


# 复用现有 TaskRequest 作为 POST body
TaskCreateRequest = TaskRequest
