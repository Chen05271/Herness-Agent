"""执行 Agent — 只读权限，不可见全局记忆，仅接收任务指令。"""

from dataclasses import dataclass
from typing import Any

from pydantic_ai import Agent, RunContext

from herness.agents.base import build_model
from herness.config import Settings
from herness.middleware.protocol import ReadOnlyMiddleware
from herness.models.worker import WORKER_KINDS, WorkerKind, WorkerOutput

_DEFAULT_WORKER_SYSTEM = """\
你是 Herness 系统的执行 Agent（Worker）。
职责：
1. 根据总管给出的任务指令完成具体工作
2. 输出结构化结果，包含 content、summary

限制：
- 你看不到全局记忆，只能使用任务指令与局部上下文
- 不要尝试规划或校验，专注执行
- 完成后设置 needs_verification=true（除非任务明确无需校验）
"""


@dataclass
class WorkerDeps:
    """执行 Agent 依赖 — 仅只读中台，无全局记忆。"""

    middleware: ReadOnlyMiddleware
    user_id: str
    task_id: str
    local_context: dict[str, Any]
    worker_type: WorkerKind = "default"


def build_worker_agent(
    settings: Settings,
    *,
    kind: WorkerKind = "default",
    system_prompt: str | None = None,
) -> Agent[WorkerDeps, WorkerOutput]:
    """构建执行 Agent 实例，可按 kind 使用专业化系统提示。"""
    if kind not in WORKER_KINDS:
        raise ValueError(f"未知 worker kind: {kind!r}")
    model = build_model(settings, temperature=settings.worker_temperature)
    prompt = system_prompt or _DEFAULT_WORKER_SYSTEM

    agent: Agent[WorkerDeps, WorkerOutput] = Agent(
        model,
        deps_type=WorkerDeps,
        output_type=WorkerOutput,
        system_prompt=prompt,
        retries=settings.max_retries_per_step,
    )

    @agent.instructions
    async def inject_local_context(ctx: RunContext[WorkerDeps]) -> str:
        """注入任务级局部上下文（不含全局记忆）。"""
        return f"## 任务局部上下文\n{ctx.deps.local_context}"

    @agent.tool
    async def fetch_task_context(ctx: RunContext[WorkerDeps]) -> str:
        """从中台只读接口获取任务上下文。"""
        context = await ctx.deps.middleware.get_task_context(
            ctx.deps.user_id, ctx.deps.task_id
        )
        return str(context)

    return agent
