"""调度器核心 — 几百行手写状态机，不依赖 LangGraph。"""

import asyncio
import hashlib
import logging
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from typing import TypeVar

from pydantic_ai import Agent

from herness.agents.critic import CriticDeps, build_critic_agent
from herness.agents.supervisor import SupervisorDeps, build_supervisor_agent
from herness.agents.worker import WorkerDeps, build_worker_agent
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
from herness.models.worker import WorkerOutput

logger = logging.getLogger(__name__)

T = TypeVar("T")

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
    ) -> None:
        self.middleware = middleware
        self.settings = settings or get_settings()
        self.config = config or OrchestratorConfig(
            max_rounds=self.settings.max_rounds,
            step_timeout_seconds=self.settings.step_timeout_seconds,
            task_timeout_seconds=self.settings.task_timeout_seconds,
            max_retries_per_step=self.settings.max_retries_per_step,
        )

        # 构建三个 Agent（节点层）；测试时可注入 mock
        self._supervisor = supervisor or build_supervisor_agent(self.settings)
        self._worker = worker or build_worker_agent(self.settings)
        self._critic = critic or build_critic_agent(self.settings)

    async def run(self, request: TaskRequest) -> TaskResult:
        """执行完整任务流程：拉记忆 → 总管规划 → Worker 执行 → Critic 校验 → 循环/完成。"""
        state = TaskState(request=request, status=TaskStatus.RUNNING)

        # 任务启动：从中台拉取预合成全局记忆，注入总管
        memory = await self.middleware.get_pre_synthesized_memory(request.user_id)
        self._log(state, AgentRole.ORCHESTRATOR, f"已加载全局记忆 v{memory.version}")

        supervisor_prompt = request.input
        critic_feedback = ""

        try:
            async with asyncio.timeout(self.config.task_timeout_seconds):
                for round_idx in range(self.config.max_rounds):
                    state.round_index = round_idx

                    # ── 1. 总管规划 ──
                    sup_out = await self._run_supervisor(
                        state, memory, supervisor_prompt, critic_feedback
                    )
                    state.last_supervisor = sup_out

                    # 检测循环规划（相同 action + instruction 哈希重复出现）
                    plan_hash = self._hash_plan(sup_out)
                    if plan_hash in state.plan_hashes:
                        return self._fail(state, "检测到循环规划，任务中止")
                    state.plan_hashes.append(plan_hash)

                    if sup_out.action == SupervisorAction.COMPLETE:
                        return await self._complete(state, sup_out.final_answer)

                    if sup_out.action == SupervisorAction.ABORT:
                        return self._abort(state, sup_out.abort_reason)

                    # ── 2. Worker 执行（无全局记忆）──
                    worker_out = await self._run_worker(state, sup_out.task_instruction)
                    state.last_worker = worker_out

                    if not worker_out.needs_verification:
                        await self._persist(state, worker_out)
                        supervisor_prompt = f"Worker 已完成：{worker_out.summary}\n请决定 complete 或继续 delegate。"
                        critic_feedback = ""
                        continue

                    # ── 3. Critic 校验 ──
                    critic_out = await self._run_critic(state, worker_out)
                    state.last_critic = critic_out

                    if critic_out.passed:
                        await self._persist(state, worker_out)
                        supervisor_prompt = (
                            f"Worker 输出已通过校验：{worker_out.summary}\n"
                            f"请给出最终答案（action=complete）。"
                        )
                        critic_feedback = ""
                    else:
                        # 校验失败 → 反馈给总管重试
                        critic_feedback = critic_out.feedback
                        supervisor_prompt = request.input
                        self._log(
                            state,
                            AgentRole.ORCHESTRATOR,
                            f"Critic 驳回：{critic_feedback}",
                        )

                return self._fail(state, f"超过最大轮数 ({self.config.max_rounds})")

        except TimeoutError:
            state.status = TaskStatus.TIMEOUT
            return TaskResult(
                task_id=state.task_id,
                status=TaskStatus.TIMEOUT,
                error="任务超时",
                rounds_used=state.round_index + 1,
                messages=state.messages,
            )
        except Exception as exc:
            return self._fail(state, f"步骤执行失败: {type(exc).__name__}: {exc}")

    # ── 内部：调用各 Agent（带单步超时 + 重试）──

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
                return await coro_factory()
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

        assert last_error is not None
        raise last_error

    async def _run_supervisor(
        self,
        state: TaskState,
        memory,
        prompt: str,
        critic_feedback: str,
    ) -> SupervisorOutput:
        """调用总管 Agent。"""
        if critic_feedback:
            prompt = f"{prompt}\n\n[Critic 反馈]\n{critic_feedback}"

        deps = SupervisorDeps(
            middleware=self.middleware,
            memory=memory,
            user_id=state.request.user_id,
            task_id=state.task_id,
        )

        async def _call() -> SupervisorOutput:
            result = await asyncio.wait_for(
                self._supervisor.run(prompt, deps=deps),
                timeout=self.config.step_timeout_seconds,
            )
            output = result.output
            self._log(state, AgentRole.SUPERVISOR, f"action={output.action.value} | {output.reasoning}")
            return output

        return await self._run_step_with_retry(state, "Supervisor", _call)

    async def _run_worker(self, state: TaskState, instruction: str) -> WorkerOutput:
        """调用执行 Agent — 故意不传全局记忆。"""
        local_context = await self.middleware.get_task_context(
            state.request.user_id, state.task_id
        )
        deps = WorkerDeps(
            middleware=self.middleware,
            user_id=state.request.user_id,
            task_id=state.task_id,
            local_context=local_context,
        )

        async def _call() -> WorkerOutput:
            result = await asyncio.wait_for(
                self._worker.run(instruction, deps=deps),
                timeout=self.config.step_timeout_seconds,
            )
            output = result.output
            self._log(state, AgentRole.WORKER, output.summary)
            return output

        return await self._run_step_with_retry(state, "Worker", _call)

    async def _run_critic(self, state: TaskState, worker_output: WorkerOutput) -> CriticOutput:
        """调用校验 Agent。"""
        deps = CriticDeps(
            middleware=self.middleware,
            user_id=state.request.user_id,
            worker_output=worker_output,
        )

        async def _call() -> CriticOutput:
            result = await asyncio.wait_for(
                self._critic.run("请校验上述 Worker 输出。", deps=deps),
                timeout=self.config.step_timeout_seconds,
            )
            output = result.output
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
        )
        await self.middleware.enqueue_dreaming_job(
            state.request.user_id,
            state.task_id,
        )
        self._log(state, AgentRole.ORCHESTRATOR, "结果已写入中台，Dreaming 任务已入队")

    async def _complete(self, state: TaskState, answer: str) -> TaskResult:
        """任务成功完成。"""
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

    # ── 工具方法 ──

    @staticmethod
    def _hash_plan(output: SupervisorOutput) -> str:
        """对总管规划做哈希，用于循环检测。"""
        raw = f"{output.action.value}|{output.task_instruction}|{output.reasoning}"
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    @staticmethod
    def _log(state: TaskState, role: AgentRole, content: str) -> None:
        """记录审计日志。"""
        msg = TaskMessage(role=role, round_index=state.round_index, content=content)
        state.messages.append(msg)
        logger.info("[%s] round=%d %s", role.value, state.round_index, content)
