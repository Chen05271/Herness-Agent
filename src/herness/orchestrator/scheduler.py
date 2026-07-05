"""调度器核心 — 几百行手写状态机，不依赖 LangGraph。"""

import asyncio
import hashlib
import logging
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from typing import Any, TypeVar
from uuid import uuid4

from pydantic_ai import Agent

from herness.agents.critic import CriticDeps, build_critic_agent
from herness.agents.critic_validation import apply_hereness_verification, apply_tool_verification
from herness.agents.registry import build_worker_registry
from herness.agents.tool_policy import resolve_allowed_worker_tools
from herness.agents.tool_trace import extract_tool_invocations
from herness.integrations.agri_commerce.factory import build_agri_commerce_client
from herness.integrations.agri_commerce.protocol import AgriCommerceClient
from herness.models.worker import WORKER_KINDS
from herness.agents.supervisor import SupervisorDeps, build_supervisor_agent
from herness.agents.worker import WorkerDeps
from herness.config import Settings, get_settings
from herness.middleware.protocol import DataMiddleware
from herness.models.critic import CriticOutput
from herness.models.supervisor import SupervisorAction, SupervisorOutput
from herness.models.task import (
    AgentRole,
    OrchestratorConfig,
    TaskMessage,
    TaskRequest,
    TaskResult,
    TaskState,
    TaskStatus,
)
from herness.models.worker import WorkerKind, WorkerOutput
from herness.observability.logging import log_event, set_trace_id
from herness.observability.metrics import MetricsRegistry, get_metrics_registry
from herness.orchestrator.cancellation import TaskCancellationRegistry, TaskCancelledError

logger = logging.getLogger(__name__)

T = TypeVar("T")

MessageListener = Callable[[TaskMessage], None]

# 调度器层可重试的瞬时错误（LLM 网络/超时等）
_RETRIABLE_EXCEPTIONS: tuple[type[BaseException], ...] = (
    TimeoutError,
    asyncio.TimeoutError,
    ConnectionError,
    OSError,
)


class Orchestrator:
    """手写调度器 — 所有 Agent 消息必须经过此层。"""

    def __init__(
        self,
        middleware: DataMiddleware,
        settings: Settings | None = None,
        config: OrchestratorConfig | None = None,
        *,
        supervisor: Agent[SupervisorDeps, SupervisorOutput] | None = None,
        worker: Agent[WorkerDeps, WorkerOutput] | None = None,
        critic: Agent[CriticDeps, CriticOutput] | None = None,
        metrics: MetricsRegistry | None = None,
        cancellation_registry: TaskCancellationRegistry | None = None,
    ) -> None:
        self.middleware = middleware
        self.settings = settings or get_settings()
        self.config = config or OrchestratorConfig(
            max_rounds=self.settings.max_rounds,
            step_timeout_seconds=self.settings.step_timeout_seconds,
            task_timeout_seconds=self.settings.task_timeout_seconds,
            max_retries_per_step=self.settings.max_retries_per_step,
            max_parallel_workers=self.settings.max_parallel_workers,
        )

        # 构建 Agent（节点层）；测试时可注入 mock
        self._supervisor = supervisor or build_supervisor_agent(self.settings)
        if worker is not None:
            self._workers: dict[WorkerKind, Agent[WorkerDeps, WorkerOutput]] = {
                kind: worker for kind in WORKER_KINDS
            }
        else:
            self._workers = build_worker_registry(self.settings)
        self._worker = worker or self._workers["default"]
        self._critic = critic or build_critic_agent(self.settings)
        self._agri_client: AgriCommerceClient | None = build_agri_commerce_client(self.settings)
        self._metrics = metrics if metrics is not None else get_metrics_registry()
        self._metrics_enabled = self.settings.metrics_enabled
        self._cancellation_registry = cancellation_registry
        self._on_message: MessageListener | None = None

    async def run(
        self,
        request: TaskRequest,
        *,
        on_message: MessageListener | None = None,
    ) -> TaskResult:
        """执行完整任务流程：拉记忆 → 总管规划 → Worker 执行 → Critic 校验 → 循环/完成。"""
        self._on_message = on_message
        state = TaskState(
            task_id=request.task_id or str(uuid4()),
            request=request,
            status=TaskStatus.RUNNING,
        )
        set_trace_id(state.task_id)

        if self._cancellation_registry is not None:
            self._cancellation_registry.register(state.task_id)

        # 任务启动：从中台拉取预合成全局记忆，注入总管
        try:
            memory, session_history = await asyncio.gather(
                self.middleware.get_pre_synthesized_memory(request.user_id),
                self.middleware.get_session_history(
                    request.session_id,
                    exclude_task_id=state.task_id,
                    limit=self.settings.session_history_limit,
                ),
            )
            self._log(
                state,
                AgentRole.ORCHESTRATOR,
                f"已加载全局记忆 v{memory.version}，会话历史 {len(session_history)} 条",
            )

            supervisor_prompt = request.input
            critic_feedback = ""

            try:
                async with asyncio.timeout(self.config.task_timeout_seconds):
                    for round_idx in range(self.config.max_rounds):
                        self._check_cancelled(state)
                        state.round_index = round_idx

                        # ── 1. 总管规划 ──
                        sup_out = await self._run_supervisor(
                            state, memory, session_history, supervisor_prompt, critic_feedback
                        )
                        state.last_supervisor = sup_out

                        # 检测循环规划（相同 action + instruction 哈希重复出现）
                        plan_hash = self._hash_plan(sup_out)
                        if plan_hash in state.plan_hashes:
                            return self._finalize(
                                state, self._fail(state, "检测到循环规划，任务中止")
                            )

                        state.plan_hashes.append(plan_hash)

                        if sup_out.action == SupervisorAction.COMPLETE:
                            return self._finalize(
                                state,
                                await self._complete(state, sup_out.final_answer),
                            )

                        if sup_out.action == SupervisorAction.ABORT:
                            return self._finalize(state, self._abort(state, sup_out.abort_reason))

                        # ── 2. Worker 执行（无全局记忆，支持并行）──
                        instructions = sup_out.delegate_instructions()
                        worker_types = sup_out.delegate_worker_types()
                        if not instructions:
                            return self._finalize(
                                state,
                                self._fail(state, "delegate 动作缺少 task_instruction(s)"),
                            )

                        worker_outputs = await self._run_workers_batch(
                            state, instructions, worker_types
                        )
                        state.last_workers = worker_outputs
                        state.last_worker = worker_outputs[-1] if worker_outputs else None

                        next_prompt, next_feedback, failed = await self._handle_worker_outputs(
                            state, worker_outputs, request.input
                        )
                        if failed:
                            return self._finalize(state, failed)

                        supervisor_prompt = next_prompt
                        critic_feedback = next_feedback

                    return self._finalize(
                        state,
                        self._fail(state, f"超过最大轮数 ({self.config.max_rounds})"),
                    )

            except TimeoutError:
                state.status = TaskStatus.TIMEOUT
                result = TaskResult(
                    task_id=state.task_id,
                    status=TaskStatus.TIMEOUT,
                    error="任务超时",
                    rounds_used=state.round_index + 1,
                    messages=state.messages,
                )
                return self._finalize(state, result)
            except TaskCancelledError:
                return self._finalize(state, self._cancelled(state))
            except asyncio.CancelledError:
                return self._finalize(state, self._cancelled(state))
            except Exception as exc:
                return self._finalize(
                    state, self._fail(state, f"步骤执行失败: {type(exc).__name__}: {exc}")
                )
        finally:
            if self._cancellation_registry is not None:
                self._cancellation_registry.unregister(state.task_id)
            self._on_message = None

    # ── 内部：调用各 Agent（带单步超时 + 重试）──

    def _check_cancelled(self, state: TaskState) -> None:
        if (
            self._cancellation_registry is not None
            and self._cancellation_registry.is_cancelled(state.task_id)
        ):
            raise TaskCancelledError()

    async def _await_with_cancel(self, state: TaskState, coro: Awaitable[T]) -> T:
        """等待协程，若收到取消信号则中断。"""
        self._check_cancelled(state)
        if self._cancellation_registry is None:
            return await coro

        task = asyncio.create_task(coro)
        event = self._cancellation_registry.get_event(state.task_id)
        if event is None:
            return await task

        cancel_wait = asyncio.create_task(event.wait())
        done, _pending = await asyncio.wait(
            {task, cancel_wait},
            return_when=asyncio.FIRST_COMPLETED,
        )
        if cancel_wait in done:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            raise TaskCancelledError()

        cancel_wait.cancel()
        try:
            await cancel_wait
        except asyncio.CancelledError:
            pass
        return await task

    async def _run_step_with_retry(
        self,
        state: TaskState,
        step_name: str,
        coro_factory: Callable[[], Awaitable[T]],
    ) -> T:
        """单步执行包装：瞬时错误时按 max_retries_per_step 重试。"""
        max_attempts = self.config.max_retries_per_step + 1
        last_error: BaseException | None = None

        for attempt in range(1, max_attempts + 1):
            try:
                self._check_cancelled(state)
                return await coro_factory()
            except TaskCancelledError:
                raise
            except _RETRIABLE_EXCEPTIONS as exc:
                last_error = exc
                if attempt >= max_attempts:
                    raise
                self._log(
                    state,
                    AgentRole.ORCHESTRATOR,
                    f"{step_name} 第 {attempt}/{max_attempts} 次失败"
                    f"（{type(exc).__name__}），重试中…",
                )
                if self._metrics_enabled:
                    self._metrics.record_step_retry(step_name)

        assert last_error is not None
        raise last_error

    async def _run_supervisor(
        self,
        state: TaskState,
        memory,
        session_history: list,
        prompt: str,
        critic_feedback: str,
    ) -> SupervisorOutput:
        """调用总管 Agent。"""
        if critic_feedback:
            prompt = f"{prompt}\n\n[Critic 反馈]\n{critic_feedback}"

        deps = SupervisorDeps(
            middleware=self.middleware,
            memory=memory,
            session_history=session_history,
            user_id=state.request.user_id,
            task_id=state.task_id,
            session_id=state.request.session_id,
        )

        async def _call() -> SupervisorOutput:
            result = await asyncio.wait_for(
                self._await_with_cancel(
                    state,
                    self._supervisor.run(prompt, deps=deps),
                ),
                timeout=self.config.step_timeout_seconds,
            )
            output = result.output
            self._log(state, AgentRole.SUPERVISOR, f"action={output.action.value} | {output.reasoning}")
            return output

        return await self._run_step_with_retry(state, "Supervisor", _call)

    async def _run_workers_batch(
        self,
        state: TaskState,
        instructions: list[str],
        worker_types: list[WorkerKind],
    ) -> list[WorkerOutput]:
        """并行 dispatch 多个 Worker（受 max_parallel_workers 限制）。"""
        local_context, allowed = await asyncio.gather(
            self.middleware.get_task_context(state.request.user_id, state.task_id),
            resolve_allowed_worker_tools(
                self.settings,
                self.middleware,
                user_id=state.request.user_id,
                task_id=state.task_id,
                metadata=state.request.metadata,
            ),
        )
        allowed_tools = frozenset(allowed)
        sem = asyncio.Semaphore(self.config.max_parallel_workers)

        async def _limited(instr: str, wtype: WorkerKind) -> WorkerOutput:
            async with sem:
                return await self._run_worker(
                    state,
                    instr,
                    worker_type=wtype,
                    local_context=local_context,
                    allowed_tools=allowed_tools,
                )

        outputs = await asyncio.gather(
            *[_limited(instr, wtype) for instr, wtype in zip(instructions, worker_types, strict=True)]
        )
        self._log(
            state,
            AgentRole.ORCHESTRATOR,
            f"并行 Worker 完成 {len(outputs)} 条",
            payload={"worker_count": len(outputs), "worker_types": worker_types},
        )
        return list(outputs)

    async def _run_worker(
        self,
        state: TaskState,
        instruction: str,
        *,
        worker_type: WorkerKind = "default",
        local_context: dict[str, Any] | None = None,
        allowed_tools: frozenset[str] | None = None,
    ) -> WorkerOutput:
        """调用执行 Agent — 故意不传全局记忆。"""
        agent = self._workers.get(worker_type, self._workers["default"])
        if local_context is None:
            local_context = await self.middleware.get_task_context(
                state.request.user_id, state.task_id
            )
        if allowed_tools is None:
            allowed = await resolve_allowed_worker_tools(
                self.settings,
                self.middleware,
                user_id=state.request.user_id,
                task_id=state.task_id,
                metadata=state.request.metadata,
            )
            allowed_tools = frozenset(allowed)
        deps = WorkerDeps(
            middleware=self.middleware,
            user_id=state.request.user_id,
            task_id=state.task_id,
            local_context=local_context,
            allowed_tools=allowed_tools,
            worker_type=worker_type,
            agri_client=self._agri_client,
        )

        async def _call() -> WorkerOutput:
            result = await asyncio.wait_for(
                self._await_with_cancel(state, agent.run(instruction, deps=deps)),
                timeout=self.config.step_timeout_seconds,
            )
            output = result.output
            invocations = extract_tool_invocations(result)
            if invocations:
                output = output.model_copy(update={"tool_invocations": invocations})
            self._log(
                state,
                AgentRole.WORKER,
                output.summary,
                payload={"worker_type": worker_type},
            )
            return output

        step_name = f"Worker({worker_type})"
        return await self._run_step_with_retry(state, step_name, _call)

    async def _handle_worker_outputs(
        self,
        state: TaskState,
        worker_outputs: list[WorkerOutput],
        original_input: str,
    ) -> tuple[str, str, TaskResult | None]:
        """处理 Worker 输出：跳过/并行 Critic 校验，返回下一轮 prompt 或终态。"""
        to_verify = [out for out in worker_outputs if out.needs_verification]
        no_verify = [out for out in worker_outputs if not out.needs_verification]

        if no_verify:
            await asyncio.gather(*[self._persist(state, out) for out in no_verify])

        if not to_verify:
            summaries = "; ".join(out.summary for out in worker_outputs)
            return (
                f"Worker 已完成：{summaries}\n请决定 complete 或继续 delegate。",
                "",
                None,
            )

        critic_results = await asyncio.gather(
            *[self._run_critic(state, out) for out in to_verify]
        )
        state.last_critic = critic_results[-1]

        failed = [c for c in critic_results if not c.passed]
        if failed:
            critic_feedback = "\n".join(c.feedback for c in failed if c.feedback)
            self._log(
                state,
                AgentRole.ORCHESTRATOR,
                f"Critic 驳回 {len(failed)}/{len(critic_results)} 条",
                payload={"rejected_count": len(failed)},
            )
            if self._metrics_enabled:
                self._metrics.record_critic_rejection(len(failed))
            return original_input, critic_feedback, None

        await asyncio.gather(*[self._persist(state, out) for out in to_verify])
        summaries = "; ".join(out.summary for out in worker_outputs)
        return (
            f"Worker 输出已通过校验：{summaries}\n请给出最终答案（action=complete）。",
            "",
            None,
        )

    async def _run_critic(self, state: TaskState, worker_output: WorkerOutput) -> CriticOutput:
        """调用校验 Agent。"""
        deps = CriticDeps(
            middleware=self.middleware,
            user_id=state.request.user_id,
            worker_output=worker_output,
        )

        async def _call() -> CriticOutput:
            result = await asyncio.wait_for(
                self._await_with_cancel(
                    state,
                    self._critic.run("请校验上述 Worker 输出。", deps=deps),
                ),
                timeout=self.config.step_timeout_seconds,
            )
            output = result.output
            output = apply_tool_verification(output, worker_output)
            if self.settings.hereness_enabled:
                output = await apply_hereness_verification(
                    output,
                    middleware=self.middleware,
                    user_id=state.request.user_id,
                    worker_output=worker_output,
                )
            self._log(
                state,
                AgentRole.CRITIC,
                f"passed={output.passed} confidence={output.confidence} | {output.feedback}",
            )
            return output

        return await self._run_step_with_retry(state, "Critic", _call)

    # ── 内部：终态处理 ──

    async def _persist(self, state: TaskState, worker_output: WorkerOutput) -> None:
        """写入中台并投递 Dreaming 队列。"""
        await self.middleware.write_task_result(
            state.request.user_id,
            state.task_id,
            worker_output,
            metadata=self._task_metadata(state),
        )
        await self.middleware.enqueue_dreaming_job(
            state.request.user_id,
            state.task_id,
        )
        self._log(state, AgentRole.ORCHESTRATOR, "结果已写入中台，Dreaming 任务已入队")

    @staticmethod
    def _task_metadata(state: TaskState, **extra: str) -> dict[str, str]:
        """任务写入中台时附带的 session 元数据。"""
        metadata = {
            "session_id": state.request.session_id,
            "input": state.request.input,
        }
        metadata.update(extra)
        return metadata

    async def _complete(self, state: TaskState, answer: str) -> TaskResult:
        """任务成功完成。"""
        await self.middleware.write_task_result(
            state.request.user_id,
            state.task_id,
            WorkerOutput(
                content=answer,
                summary=answer[:200],
                needs_verification=False,
            ),
            metadata=self._task_metadata(state, final_answer=answer),
        )
        state.status = TaskStatus.COMPLETED
        state.finished_at = datetime.now(timezone.utc)
        self._log(state, AgentRole.ORCHESTRATOR, "任务完成")
        return TaskResult(
            task_id=state.task_id,
            status=TaskStatus.COMPLETED,
            answer=answer,
            rounds_used=state.round_index + 1,
            messages=state.messages,
        )

    def _abort(self, state: TaskState, reason: str) -> TaskResult:
        """总管主动中止。"""
        state.status = TaskStatus.ABORTED
        state.finished_at = datetime.now(timezone.utc)
        return TaskResult(
            task_id=state.task_id,
            status=TaskStatus.ABORTED,
            error=reason,
            rounds_used=state.round_index + 1,
            messages=state.messages,
        )

    def _cancelled(self, state: TaskState) -> TaskResult:
        """API / 用户主动取消。"""
        state.status = TaskStatus.CANCELLED
        state.finished_at = datetime.now(timezone.utc)
        self._log(state, AgentRole.ORCHESTRATOR, "任务已取消")
        return TaskResult(
            task_id=state.task_id,
            status=TaskStatus.CANCELLED,
            error="任务已取消",
            rounds_used=state.round_index + 1,
            messages=state.messages,
        )

    def _fail(self, state: TaskState, error: str) -> TaskResult:
        """任务失败。"""
        state.status = TaskStatus.FAILED
        state.finished_at = datetime.now(timezone.utc)
        logger.warning("任务失败 task_id=%s error=%s", state.task_id, error)
        return TaskResult(
            task_id=state.task_id,
            status=TaskStatus.FAILED,
            error=error,
            rounds_used=state.round_index + 1,
            messages=state.messages,
        )

    def _finalize(self, state: TaskState, result: TaskResult) -> TaskResult:
        """记录任务终态指标与结构化日志。"""
        if state.finished_at is None:
            state.finished_at = datetime.now(timezone.utc)
        duration = (state.finished_at - state.started_at).total_seconds()
        if self._metrics_enabled:
            self._metrics.record_task_finished(
                result.status,
                rounds=result.rounds_used,
                duration_seconds=duration,
            )
        log_event(
            logger,
            logging.INFO,
            "task_finished",
            task_id=state.task_id,
            status=result.status.value,
            rounds_used=result.rounds_used,
            duration_seconds=round(duration, 3),
        )
        return result

    # ── 工具方法 ──

    @staticmethod
    def _hash_plan(output: SupervisorOutput) -> str:
        """对总管规划做哈希，用于循环检测。"""
        instructions = "|".join(output.delegate_instructions())
        types = "|".join(output.delegate_worker_types())
        raw = f"{output.action.value}|{instructions}|{types}|{output.reasoning}"
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    def _log(
        self,
        state: TaskState,
        role: AgentRole,
        content: str,
        *,
        payload: dict | None = None,
    ) -> None:
        """记录审计日志与结构化 trace。"""
        msg = TaskMessage(
            role=role,
            round_index=state.round_index,
            content=content,
            payload=payload or {},
        )
        state.messages.append(msg)
        if self._on_message is not None:
            self._on_message(msg)
        log_event(
            logger,
            logging.INFO,
            "orchestrator_step",
            role=role.value,
            round_index=state.round_index,
            message=content,
            task_id=state.task_id,
            **(payload or {}),
        )
