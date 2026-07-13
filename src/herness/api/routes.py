"""HTTP 路由 — /v1/tasks。"""

import asyncio
import json
import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse

from herness.agents.ppt_tools import resolve_artifact_path
from herness.agents.tools import WorkerToolError

from herness.api.live import TaskLiveHub
from herness.api.schemas import (
    PublicConfigFeatures,
    PublicConfigLimits,
    PublicConfigResponse,
    PublicSkillInfo,
    SessionUsageResponse,
    TaskCancelResponse,
    TaskCreateRequest,
    TaskMessagesResponse,
    TaskStatusResponse,
    TaskSubmitResponse,
    UserUsageResponse,
)
from herness.api.security import check_user_rate_limit, require_api_key
from herness.personas import PersonaValidationError, prepare_task_request
from herness.api.store import TaskStore
from herness.models.task import TaskRequest, TaskResult, TaskStatus, TokenUsage
from herness.api.webhook import notify_task_webhook
from herness.models.usage import UsageSource
from herness.observability.usage_recorder import record_usage_event
from herness.observability.usage_store import UsageStore
from herness.orchestrator.cancellation import TaskCancellationRegistry
from herness.orchestrator.scheduler import Orchestrator
from herness.skills.loader import list_available_skills

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
    task_request: TaskRequest,
    result: TaskResult,
) -> None:
    await record_usage_event(
        source=UsageSource.ORCHESTRATOR,
        usage=result.usage,
        user_id=task_request.user_id,
        session_id=task_request.session_id,
        event_id=result.task_id,
        status=result.status,
    )


async def _check_token_budget(
    usage_store: UsageStore,
    settings,
    user_id: str,
    session_id: str,
) -> None:
    if settings.token_budget_per_user > 0:
        user_usage = await usage_store.get_user_usage(user_id)
        if user_usage.total_tokens >= settings.token_budget_per_user:
            raise HTTPException(status_code=429, detail="用户 token 配额已用尽")
    if settings.token_budget_per_session > 0:
        session_usage = await usage_store.get_session_usage(user_id, session_id)
        if session_usage.total_tokens >= settings.token_budget_per_session:
            raise HTTPException(status_code=429, detail="会话 token 配额已用尽")


def _resolve_webhook_url(settings, metadata: dict) -> str:
    override = str(metadata.get("webhook_url") or "").strip()
    return override or settings.webhook_url.strip()


async def _execute_task(
    store: TaskStore,
    orchestrator: Orchestrator,
    live_hub: TaskLiveHub,
    cancellation_registry: TaskCancellationRegistry,
    usage_store: UsageStore,
    task_request: TaskRequest,
    *,
    settings,
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
        await _persist_task_usage(task_request, result)
    except Exception:
        logger.exception("任务执行异常 task_id=%s", task_id)
        failed = TaskResult(
            task_id=task_id,
            status=TaskStatus.FAILED,
            error="任务执行异常",
        )
        store.complete(failed)
        await _persist_task_usage(task_request, failed)
    finally:
        record = store.get(task_id)
        status = record.status if record else TaskStatus.FAILED
        await live_hub.finish_task(task_id, status)
        if record and record.result:
            webhook_url = _resolve_webhook_url(settings, task_request.metadata)
            await notify_task_webhook(
                webhook_url,
                task_request=task_request,
                result=record.result,
                timeout_seconds=settings.webhook_timeout_seconds,
            )


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
    settings = request.app.state.settings

    await _check_token_budget(
        usage_store,
        settings,
        prepared.user_id,
        prepared.session_id,
    )

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
        settings=settings,
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


@router.get("/users/{user_id}/usage", response_model=UserUsageResponse)
async def get_user_usage(user_id: str, request: Request) -> UserUsageResponse:
    """查询用户累计 token 用量（含 Orchestrator / Dreaming / Embedding 等）。"""
    usage_store = _get_usage_store(request)
    usage = await usage_store.get_user_usage(user_id)
    return UserUsageResponse(user_id=user_id, usage=usage)


@router.get("/config/public", response_model=PublicConfigResponse)
async def get_public_config(request: Request) -> PublicConfigResponse:
    """返回非敏感公开配置，供前端展示能力与配额上限。"""
    settings = request.app.state.settings
    skill_items = list_available_skills(settings=settings)
    return PublicConfigResponse(
        llm_model=settings.llm_model,
        features=PublicConfigFeatures(
            rag_enabled=settings.rag_enabled,
            dreaming_enabled=settings.dreaming_enabled,
            hereness_enabled=settings.hereness_enabled,
            agri_commerce_enabled=settings.agri_commerce_enabled,
            otel_enabled=settings.otel_enabled,
            skills_enabled=settings.skills_enabled,
            ppt_enabled=settings.worker_tools_ppt_enabled,
        ),
        limits=PublicConfigLimits(
            token_budget_per_user=settings.token_budget_per_user,
            token_budget_per_session=settings.token_budget_per_session,
        ),
        skills=[
            PublicSkillInfo(
                name=item["name"],
                description=item.get("description", ""),
                worker_kind=item.get("worker_kind", "default"),
            )
            for item in skill_items
        ],
    )


@router.get("/tasks/{task_id}/artifacts/{artifact_path:path}")
async def download_task_artifact(
    task_id: str,
    artifact_path: str,
    request: Request,
) -> FileResponse:
    """下载任务产物（如生成的 PPT）。"""
    settings = request.app.state.settings
    store = _get_store(request)
    record = store.get(task_id)
    if record is None:
        raise HTTPException(status_code=404, detail="任务不存在")

    normalized = artifact_path.replace("\\", "/").lstrip("/")
    if not normalized.startswith(f"{task_id}/"):
        raise HTTPException(status_code=403, detail="无权访问该产物")

    try:
        file_path = resolve_artifact_path(settings, normalized)
    except WorkerToolError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if not file_path.is_file():
        raise HTTPException(status_code=404, detail="产物文件不存在")

    return FileResponse(
        path=file_path,
        filename=file_path.name,
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
    )
