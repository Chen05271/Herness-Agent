"""HTTP 路由 — /v1/tasks。"""

import logging

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request

from herness.api.schemas import (
    TaskCreateRequest,
    TaskMessagesResponse,
    TaskStatusResponse,
    TaskSubmitResponse,
)
from herness.api.store import TaskStore
from herness.models.task import TaskRequest, TaskStatus
from herness.orchestrator.scheduler import Orchestrator

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1", tags=["tasks"])


def _get_store(request: Request) -> TaskStore:
    return request.app.state.store


def _get_orchestrator(request: Request) -> Orchestrator:
    return request.app.state.orchestrator


async def _execute_task(
    store: TaskStore,
    orchestrator: Orchestrator,
    task_request: TaskRequest,
) -> None:
    """后台执行调度器并回写任务状态。"""
    store.mark_running(task_request.task_id or "")
    try:
        result = await orchestrator.run(task_request)
        store.complete(result)
    except Exception:
        logger.exception("任务执行异常 task_id=%s", task_request.task_id)
        from herness.models.task import TaskResult

        store.complete(
            TaskResult(
                task_id=task_request.task_id or "",
                status=TaskStatus.FAILED,
                error="任务执行异常",
            )
        )


@router.post("/tasks", response_model=TaskSubmitResponse, status_code=202)
async def submit_task(
    body: TaskCreateRequest,
    background_tasks: BackgroundTasks,
    request: Request,
) -> TaskSubmitResponse:
    """提交任务，异步执行，返回 task_id。"""
    store = _get_store(request)
    orchestrator = _get_orchestrator(request)

    record = store.create(body)
    background_tasks.add_task(_execute_task, store, orchestrator, record.request)

    return TaskSubmitResponse(
        task_id=record.task_id,
        status=record.status,
        created_at=record.created_at,
    )


@router.get("/tasks/{task_id}", response_model=TaskStatusResponse)
async def get_task(task_id: str, request: Request) -> TaskStatusResponse:
    """查询任务状态与结果。"""
    store = _get_store(request)
    record = store.get(task_id)
    if record is None:
        raise HTTPException(status_code=404, detail="任务不存在")

    result = record.result
    return TaskStatusResponse(
        task_id=record.task_id,
        status=record.status,
        answer=result.answer if result else "",
        error=result.error if result else "",
        rounds_used=result.rounds_used if result else 0,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


@router.get("/tasks/{task_id}/messages", response_model=TaskMessagesResponse)
async def get_task_messages(task_id: str, request: Request) -> TaskMessagesResponse:
    """查询任务审计日志。"""
    store = _get_store(request)
    record = store.get(task_id)
    if record is None:
        raise HTTPException(status_code=404, detail="任务不存在")

    return TaskMessagesResponse(task_id=task_id, messages=store.messages(task_id))
