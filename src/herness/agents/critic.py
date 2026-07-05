"""校验 Agent — Schema 校验 + Hereness 信念库事实一致性检查。"""

from dataclasses import dataclass

from pydantic_ai import Agent, RunContext

from herness.agents.base import build_model
from herness.config import Settings
from herness.middleware.protocol import ReadOnlyMiddleware
from herness.models.critic import CriticOutput
from herness.models.worker import WorkerOutput


@dataclass
class CriticDeps:
    """校验 Agent 依赖 — 只读中台 + Hereness 信念库查询。"""

    middleware: ReadOnlyMiddleware
    user_id: str
    worker_output: WorkerOutput


CRITIC_SYSTEM = """\
你是 Herness 系统的校验 Agent（Critic）。
职责：
1. 检查 Worker 输出的结构完整性与逻辑自洽
2. 提取关键事实声明，与 Hereness 信念库比对
3. 给出 passed=true/false 及可执行的 feedback

规则：
- 结构明显缺失或自相矛盾 → passed=false
- 事实与信念库 contradicted → passed=false
- 无法证伪但结构合理 → 可 passed=true，confidence 适当降低
"""


def build_critic_agent(settings: Settings) -> Agent[CriticDeps, CriticOutput]:
    """构建校验 Agent 实例。"""
    model = build_model(settings, temperature=settings.critic_temperature)

    agent: Agent[CriticDeps, CriticOutput] = Agent(
        model,
        deps_type=CriticDeps,
        output_type=CriticOutput,
        system_prompt=CRITIC_SYSTEM,
        retries=settings.max_retries_per_step,
    )

    @agent.instructions
    async def inject_worker_output(ctx: RunContext[CriticDeps]) -> str:
        """注入待校验的 Worker 输出。"""
        wo = ctx.deps.worker_output
        return (
            f"## 待校验内容\n"
            f"摘要：{wo.summary}\n"
            f"内容：{wo.content}\n"
            f"产物：{wo.artifacts}"
        )

    @agent.tool
    async def check_beliefs(ctx: RunContext[CriticDeps], claims: list[str]) -> str:
        """查询 Hereness 信念库，核实事实声明。"""
        results = await ctx.deps.middleware.query_beliefs(ctx.deps.user_id, claims)
        return str(results)

    return agent
