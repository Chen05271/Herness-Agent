"""任务状态存储 — 内存或 Redis 实现。"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from herness.config import Settings
from herness.models.task import TaskMessage, TaskRequest, TaskResult, TaskStatus
from herness.redis.client import create_sync_redis
from herness.redis.keys import TASK_PREFIX


@dataclass
class TaskRecord:
    """单次 API 任务的生命周期记录。"""

    task_id: str
    request: TaskRequest
    status: TaskStatus = TaskStatus.PENDING
    result: TaskResult | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class TaskStore:
    """线程安全的内存任务仓库（单进程）。"""

    def __init__(self) -> None:
        self._tasks: dict[str, TaskRecord] = {}

    def create(self, request: TaskRequest) -> TaskRecord:
        """登记新任务，返回带 task_id 的记录。"""
        task_id = request.task_id or str(uuid4())
        req = request.model_copy(update={"task_id": task_id})
        record = TaskRecord(task_id=task_id, request=req, status=TaskStatus.PENDING)
        self._tasks[task_id] = record
        return record

    def get(self, task_id: str) -> TaskRecord | None:
        return self._tasks.get(task_id)

    def mark_running(self, task_id: str) -> None:
        record = self._require(task_id)
        record.status = TaskStatus.RUNNING
        record.updated_at = datetime.now(timezone.utc)

    def mark_cancelling(self, task_id: str) -> None:
        record = self._require(task_id)
        if record.status == TaskStatus.RUNNING:
            record.updated_at = datetime.now(timezone.utc)

    def complete(self, result: TaskResult) -> None:
        record = self._require(result.task_id)
        record.status = result.status
        record.result = result
        record.updated_at = datetime.now(timezone.utc)

    def messages(self, task_id: str) -> list[TaskMessage]:
        record = self._require(task_id)
        if record.result:
            return record.result.messages
        return []

    def close(self) -> None:
        """内存实现无需释放资源。"""

    def _require(self, task_id: str) -> TaskRecord:
        record = self._tasks.get(task_id)
        if record is None:
            raise KeyError(task_id)
        return record


class RedisTaskStore:
    """基于 Redis 的任务状态存储，支持多进程/重启后短期可查。"""

    def __init__(
        self,
        redis_url: str,
        *,
        ttl_seconds: int = 86400,
        redis_client: Any = None,
    ) -> None:
        self._redis = redis_client or create_sync_redis(redis_url)
        self._ttl = ttl_seconds

    def _key(self, task_id: str) -> str:
        return f"{TASK_PREFIX}{task_id}"

    def _serialize(self, record: TaskRecord) -> str:
        payload = {
            "task_id": record.task_id,
            "request": record.request.model_dump(mode="json"),
            "status": record.status.value,
            "result": record.result.model_dump(mode="json") if record.result else None,
            "created_at": record.created_at.isoformat(),
            "updated_at": record.updated_at.isoformat(),
        }
        return json.dumps(payload, ensure_ascii=False)

    def _deserialize(self, raw: str) -> TaskRecord:
        data = json.loads(raw)
        return TaskRecord(
            task_id=data["task_id"],
            request=TaskRequest.model_validate(data["request"]),
            status=TaskStatus(data["status"]),
            result=TaskResult.model_validate(data["result"]) if data["result"] else None,
            created_at=datetime.fromisoformat(data["created_at"]),
            updated_at=datetime.fromisoformat(data["updated_at"]),
        )

    def _save(self, record: TaskRecord) -> None:
        self._redis.set(self._key(record.task_id), self._serialize(record), ex=self._ttl)

    def create(self, request: TaskRequest) -> TaskRecord:
        task_id = request.task_id or str(uuid4())
        req = request.model_copy(update={"task_id": task_id})
        record = TaskRecord(task_id=task_id, request=req, status=TaskStatus.PENDING)
        self._save(record)
        return record

    def get(self, task_id: str) -> TaskRecord | None:
        raw = self._redis.get(self._key(task_id))
        if raw is None:
            return None
        return self._deserialize(raw)

    def mark_running(self, task_id: str) -> None:
        record = self._require(task_id)
        record.status = TaskStatus.RUNNING
        record.updated_at = datetime.now(timezone.utc)
        self._save(record)

    def mark_cancelling(self, task_id: str) -> None:
        record = self._require(task_id)
        if record.status == TaskStatus.RUNNING:
            record.updated_at = datetime.now(timezone.utc)
            self._save(record)

    def complete(self, result: TaskResult) -> None:
        record = self._require(result.task_id)
        record.status = result.status
        record.result = result
        record.updated_at = datetime.now(timezone.utc)
        self._save(record)

    def messages(self, task_id: str) -> list[TaskMessage]:
        record = self._require(task_id)
        if record.result:
            return record.result.messages
        return []

    def close(self) -> None:
        self._redis.close()

    def _require(self, task_id: str) -> TaskRecord:
        record = self.get(task_id)
        if record is None:
            raise KeyError(task_id)
        return record


def create_task_store(settings: Settings) -> TaskStore | RedisTaskStore:
    """按 REDIS_URL 选择任务存储后端。"""
    if settings.redis_url:
        return RedisTaskStore(
            settings.redis_url,
            ttl_seconds=settings.redis_task_ttl_seconds,
        )
    return TaskStore()


def close_task_store(store: Any) -> None:
    """释放任务存储资源。"""
    close = getattr(store, "close", None)
    if close is not None:
        close()
