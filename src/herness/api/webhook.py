"""任务完成 Webhook 通知。"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from herness.models.task import TaskRequest, TaskResult

logger = logging.getLogger(__name__)


async def notify_task_webhook(
    url: str,
    *,
    task_request: TaskRequest,
    result: TaskResult,
    timeout_seconds: float = 5.0,
) -> None:
    """任务终态时 POST 通知外部系统（失败仅记日志，不阻断主流程）。"""
    if not url:
        return

    payload: dict[str, Any] = {
        "event": "task.finished",
        "task_id": result.task_id,
        "user_id": task_request.user_id,
        "session_id": task_request.session_id,
        "status": result.status.value,
        "answer": result.answer,
        "error": result.error,
        "rounds_used": result.rounds_used,
        "usage": result.usage.model_dump(),
        "metadata": dict(task_request.metadata),
    }

    try:
        async with httpx.AsyncClient(timeout=timeout_seconds) as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()
    except Exception:
        logger.exception("webhook delivery failed url=%s task_id=%s", url, result.task_id)
