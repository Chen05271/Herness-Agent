"""总管 Agent — 拥有中台读写权限，注入预合成全局记忆，temp=0。"""

from dataclasses import dataclass

from pydantic_ai import Agent, RunContext

from herness.agents.base import build_model
from herness.config import Settings
from herness.middleware.memory import PreSynthesizedMemory
from herness.middleware.protocol import DataMiddleware
from herness.models.supervisor import SupervisorOutput


@dataclass
class SupervisorDeps:
    """总管依赖注入 — 包含中台读写接口与全局记忆。"""

    middleware: DataMiddleware
    memory: PreSynthesizedMemory
    user_id: str
    task_id: str


SUPERVISOR_SYSTEM = """\
你是 Herness 系统的总管 Agent（Supervisor）。
职责：
1. 理解用户意图，决定下一步动作（delegate / complete / abort）
2. 将复杂任务分解为清晰的 Worker 指令
3. 综合 Worker 执行结果与 Critic 反馈，给出最终答案

规则：
- action=delegate 时必须给出 task_instruction
- action=complete 时必须给出 final_answer
- action=abort 时必须给出 abort_reason
- 你只能规划，不直接执行具体操作
"""


def build_supervisor_agent(settings: Settings) -> Agent[SupervisorDeps, SupervisorOutput]:
    """构建总管 Agent 实例。"""
    model = build_model(settings, temperature=settings.supervisor_temperature)

    agent: Agent[SupervisorDeps, SupervisorOutput] = Agent(
        model,
        deps_type=SupervisorDeps,
        output_type=SupervisorOutput,
        system_prompt=SUPERVISOR_SYSTEM,
        retries=settings.max_retries_per_step,
    )

    @agent.instructions
    async def inject_memory(ctx: RunContext[SupervisorDeps]) -> str:
        """动态注入预合成全局记忆（仅总管可见）。"""
        return ctx.deps.memory.to_prompt_block()

    @agent.tool
    async def read_task_history(ctx: RunContext[SupervisorDeps]) -> str:
        """从中台读取当前任务历史（总管专用工具）。"""
        context = await ctx.deps.middleware.get_task_context(
            ctx.deps.user_id, ctx.deps.task_id
        )
        return str(context)

    return agent
