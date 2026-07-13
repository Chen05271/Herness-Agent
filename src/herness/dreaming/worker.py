"""Dreaming 队列消费者 — 独立进程运行，异步更新用户记忆。"""

from __future__ import annotations

import asyncio
import inspect
import logging
from typing import Any

from herness.config import Settings
from herness.dreaming.synthesizer import MemorySynthesizer
from herness.observability.logging import log_event
from herness.observability.metrics import get_metrics_registry
from herness.observability.tracing import setup_tracing, shutdown_tracing, start_span
from herness.models.usage import UsageSource
from herness.observability.usage_recorder import record_usage_event

logger = logging.getLogger(__name__)


class DreamingWorker:
    """从 Redis / Postgres / 内存队列消费 Dreaming 任务。"""

    def __init__(
        self,
        middleware: Any,
        synthesizer: MemorySynthesizer,
        settings: Settings,
    ) -> None:
        self._middleware = middleware
        self._synthesizer = synthesizer
        self._settings = settings
        self._metrics = get_metrics_registry()

    async def _dequeue(self) -> tuple[str, str] | None:
        dequeue = getattr(self._middleware, "dequeue_dreaming_job", None)
        if dequeue is None:
            log_event(logger, logging.WARNING, "dreaming_dequeue_unavailable")
            return None
        timeout = self._settings.dreaming_poll_timeout_seconds
        return await dequeue(timeout=timeout)

    async def _mark_done(self, user_id: str, task_id: str, *, success: bool) -> None:
        mark = getattr(self._middleware, "mark_dreaming_job_done", None)
        if mark is not None:
            await mark(user_id, task_id, success=success)

    async def _invalidate_cache(self, user_id: str) -> None:
        invalidate = getattr(self._middleware, "invalidate_memory_cache", None)
        if invalidate is not None:
            await invalidate(user_id)

    async def process_job(self, user_id: str, task_id: str) -> None:
        """处理单条 Dreaming 任务：读结果 → 合成 → 写回记忆与信念。"""
        with start_span(
            "dreaming.process_job",
            task_id=task_id,
            attributes={"herness.user_id": user_id},
        ):
            await self._process_job_inner(user_id, task_id)

    async def _process_job_inner(self, user_id: str, task_id: str) -> None:
        log_event(
            logger,
            logging.INFO,
            "dreaming_job_started",
            user_id=user_id,
            task_id=task_id,
        )

        get_result = getattr(self._middleware, "get_task_result", None)
        if get_result is None:
            raise RuntimeError("中台未实现 get_task_result，无法消费 Dreaming 任务")

        task_result = await get_result(user_id, task_id)
        if task_result is None:
            raise ValueError(f"任务结果不存在: user_id={user_id} task_id={task_id}")

        current = await self._middleware.get_pre_synthesized_memory(user_id)
        synthesis = await self._synthesizer.synthesize(
            current=current,
            task_result=task_result,
            task_id=task_id,
        )
        updated = synthesis.memory

        session_id = ""
        get_metadata = getattr(self._middleware, "get_task_metadata", None)
        if get_metadata is not None:
            meta = await get_metadata(user_id, task_id)
            session_id = str(meta.get("session_id") or "")

        await record_usage_event(
            source=UsageSource.DREAMING,
            usage=synthesis.usage,
            user_id=user_id,
            session_id=session_id,
            event_id=f"{task_id}:dreaming",
        )

        save = getattr(self._middleware, "save_pre_synthesized_memory", None)
        if save is None:
            raise RuntimeError("中台未实现 save_pre_synthesized_memory")

        await save(updated)

        seed_belief = getattr(self._middleware, "seed_belief", None)
        if seed_belief is not None:
            for belief in synthesis.new_beliefs:
                kwargs = {
                    "source": "dreaming",
                    "confidence": belief.confidence,
                }
                if inspect.iscoroutinefunction(seed_belief):
                    await seed_belief(user_id, belief.fact, **kwargs)
                else:
                    seed_belief(user_id, belief.fact, **kwargs)

        await self._invalidate_cache(user_id)

        log_event(
            logger,
            logging.INFO,
            "dreaming_job_completed",
            user_id=user_id,
            task_id=task_id,
            memory_version=updated.version,
        )

    async def run_once(self) -> bool:
        """消费一条任务；无任务时返回 False。"""
        job = await self._dequeue()
        if job is None:
            return False

        user_id, task_id = job
        max_retries = self._settings.dreaming_max_retries
        backoff = self._settings.dreaming_retry_backoff_seconds
        last_exc: Exception | None = None

        for attempt in range(1, max_retries + 1):
            try:
                await self.process_job(user_id, task_id)
                await self._mark_done(user_id, task_id, success=True)
                if self._settings.metrics_enabled:
                    self._metrics.record_dreaming_job(success=True)
                return True
            except Exception as exc:
                last_exc = exc
                if attempt < max_retries:
                    log_event(
                        logger,
                        logging.WARNING,
                        "dreaming_job_retry",
                        user_id=user_id,
                        task_id=task_id,
                        attempt=attempt,
                        max_retries=max_retries,
                        error=str(exc),
                    )
                    await asyncio.sleep(backoff * attempt)
                    continue

                log_event(
                    logger,
                    logging.ERROR,
                    "dreaming_job_failed",
                    user_id=user_id,
                    task_id=task_id,
                    attempts=max_retries,
                    error=str(exc),
                )
                await self._mark_done(user_id, task_id, success=False)
                if self._settings.metrics_enabled:
                    self._metrics.record_dreaming_job(success=False)
                raise last_exc from None

    async def run_forever(self) -> None:
        """持续消费队列，直到进程被中断。"""
        log_event(logger, logging.INFO, "dreaming_worker_started")
        while True:
            try:
                processed = await self.run_once()
            except Exception:
                await asyncio.sleep(1.0)
                continue
            if not processed:
                await asyncio.sleep(0.1)
