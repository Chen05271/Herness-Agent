"""HTTP 路由 — /v1/tasks。"""

import asyncio
import json
import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse

from herness.api.live import TaskLiveHub
from herness.api.schemas import (
    SessionUsageResponse,
    TaskCancelResponse,
    TaskCreateRequest,
    TaskMessagesResponse,
    TaskStatusResponse,
    TaskSubmitResponse,
)
from herness.api.security import check_user_rate_limit, require_api_key
from herness.personas import PersonaValidationError, prepare_task_request
from herness.api.store import TaskStore
from herness.models.task import TaskRequest, TaskResult, TaskStatus, TokenUsage
from herness.observability.usage_store import UsageStore
from herness.orchestrator.cancellation import TaskCancellationRegistry
from herness.orchestrator.scheduler import Orchestrator

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/v1",
    tags=["tasks"],
    dependencies=[Depends(require_api_key)],
)


def _get_store(request: Request) -> TaskStore:
    return request.app.state.store


def _get_orchestrator(request: Request) -> Orchestrator:
    return request.app.state.orchestrator


def _get_live_hub(request: Request) -> TaskLiveHub:
    return request.app.state.live_hub


def _get_cancellation_registry(request: Request) -> TaskCancellationRegistry:
    return request.app.state.cancellation_registry


def _get_usage_store(request: Request) -> UsageStore:
    return request.app.state.usage_store


async def _persist_task_usage(
    usage_store: UsageStore,
    task_request: TaskRequest,
    result: TaskResult,
) -> None:
    if result.usage.total_tokens <= 0 and result.usage.requests <= 0:
        return
    await usage_store.record_task_usage(
        task_id=result.task_id,
        user_id=task_request.user_id,
        session_id=task_request.session_id,
        status=result.status,
        usage=result.usage,
    )


async def _execute_task(
    store: TaskStore,
    orchestrator: Orchestrator,
    live_hub: TaskLiveHub,
    cancellation_registry: TaskCancellationRegistry,
    usage_store: UsageStore,
    task_request: TaskRequest,
) -> None:
    """后台执行调度器并回写任务状态。"""
    task_id = task_request.task_id or ""
    if cancellation_registry.is_pre_cancelled(task_id):
        store.complete(
            TaskResult(
                task_id=task_id,
                status=TaskStatus.CANCELLED,
                error="任务已取消",
            )
        )
        return

    await live_hub.start_task(task_id)
    listener = live_hub.make_listener(task_id)
    store.mark_running(task_id)
    try:
        result = await orchestrator.run(task_request, on_message=listener)
        store.complete(result)
        await _persist_task_usage(usage_store, task_request, result)
    except Exception:
        logger.exception("任务执行异常 task_id=%s", task_id)
        store.complete(
            TaskResult(
                task_id=task_id,
                status=TaskStatus.FAILED,
                error="任务执行异常",
            )
        )
    finally:
        record = store.get(task_id)
        status = record.status if record else TaskStatus.FAILED
        await live_hub.finish_task(task_id, status)


@router.post("/tasks", response_model=TaskSubmitResponse, status_code=202)
async def submit_task(
    body: TaskCreateRequest,
    background_tasks: BackgroundTasks,
    request: Request,
) -> TaskSubmitResponse:
    """提交任务，异步执行，返回 task_id。"""
    try:
        prepared = prepare_task_request(body, settings=request.app.state.settings)
    except PersonaValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    check_user_rate_limit(request, prepared.user_id)
    store = _get_store(request)
    orchestrator = _get_orchestrator(request)
    live_hub = _get_live_hub(request)
    cancellation_registry = _get_cancellation_registry(request)
    usage_store = _get_usage_store(request)

    record = store.create(prepared)
    cancellation_registry.mark_pending(record.task_id)
    background_tasks.add_task(
        _execute_task,
        store,
        orchestrator,
        live_hub,
        cancellation_registry,
        usage_store,
        record.request,
    )

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
        usage=result.usage if result else TokenUsage(),
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


@router.delete("/tasks/{task_id}", response_model=TaskCancelResponse)
async def cancel_task(task_id: str, request: Request) -> TaskCancelResponse:
    """取消 PENDING 或 RUNNING 任务。"""
    store = _get_store(request)
    cancellation_registry = _get_cancellation_registry(request)
    record = store.get(task_id)
    if record is None:
        raise HTTPException(status_code=404, detail="任务不存在")

    if record.status in {
        TaskStatus.COMPLETED,
        TaskStatus.FAILED,
        TaskStatus.TIMEOUT,
        TaskStatus.ABORTED,
        TaskStatus.CANCELLED,
    }:
        raise HTTPException(status_code=409, detail=f"任务已终态：{record.status.value}")

    cancellation_registry.request_cancel(task_id)
    if record.status == TaskStatus.PENDING:
        store.complete(
            TaskResult(
                task_id=task_id,
                status=TaskStatus.CANCELLED,
                error="任务已取消",
            )
        )
    else:
        store.mark_cancelling(task_id)

    return TaskCancelResponse(task_id=task_id, status=TaskStatus.CANCELLED)


@router.get("/tasks/{task_id}/messages", response_model=TaskMessagesResponse)
async def get_task_messages(task_id: str, request: Request) -> TaskMessagesResponse:
    """查询任务审计日志。"""
    store = _get_store(request)
    live_hub = _get_live_hub(request)
    record = store.get(task_id)
    if record is None:
        raise HTTPException(status_code=404, detail="任务不存在")

    if record.status == TaskStatus.RUNNING:
        messages = await live_hub.messages(task_id)
        return TaskMessagesResponse(task_id=task_id, messages=messages)

    return TaskMessagesResponse(task_id=task_id, messages=store.messages(task_id))


@router.get("/tasks/{task_id}/stream")
async def stream_task_messages(task_id: str, request: Request) -> StreamingResponse:
    """SSE 流式推送审计日志。"""
    store = _get_store(request)
    live_hub = _get_live_hub(request)
    record = store.get(task_id)
    if record is None:
        raise HTTPException(status_code=404, detail="任务不存在")

    async def event_generator():
        async for message in live_hub.stream(task_id):
            payload = message.model_dump(mode="json")
            yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
            await asyncio.sleep(0)

        record_after = store.get(task_id)
        if record_after and record_after.result:
            terminal = {
                "event": "task_finished",
                "task_id": task_id,
                "status": record_after.status.value,
                "usage": (
                    record_after.result.usage.model_dump()
                    if record_after.result
                    else TokenUsage().model_dump()
                ),
            }
            yield f"data: {json.dumps(terminal, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/sessions/{session_id}/usage", response_model=SessionUsageResponse)
async def get_session_usage(
    session_id: str,
    user_id: str,
    request: Request,
) -> SessionUsageResponse:
    """查询同 session 累计 token 用量。"""
    usage_store = _get_usage_store(request)
    usage = await usage_store.get_session_usage(user_id, session_id)
    return SessionUsageResponse(
        user_id=user_id,
        session_id=session_id,
        usage=usage,
    )
