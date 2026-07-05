"""命令行入口 — 本地演示调度流程（需 vLLM 服务运行）。

注意：本项目要求 Python >= 3.11，请使用 py -3.11 运行：
    py -3.11 -m herness.main "你的问题"
或：
    .\\run.ps1 "你的问题"
"""

import asyncio
import sys

from herness.config import get_settings
from herness.middleware.stub import InMemoryMiddleware
from herness.middleware.memory import SynthesizedMemorySlice
from herness.models.task import TaskRequest
from herness.observability.logging import configure_logging
from herness.orchestrator.scheduler import Orchestrator

configure_logging(structured=get_settings().structured_logging)


async def run_demo(user_input: str, user_id: str = "demo_user") -> None:
    """运行一次演示任务。"""
    settings = get_settings()
    middleware = InMemoryMiddleware()

    # 预置演示数据（后续由 Dreaming 离线生成）
    middleware.seed_memory(
        user_id=user_id,
        summary="演示用户，偏好简洁回答。",
        slices=[
            SynthesizedMemorySlice(category="profile", content="语言：中文"),
            SynthesizedMemorySlice(category="facts", content="项目名：Herness Agent"),
        ],
    )
    middleware.seed_belief(user_id, "Herness Agent 是基于 PydanticAI 的多 Agent 框架")

    orchestrator = Orchestrator(middleware=middleware, settings=settings)
    request = TaskRequest(user_id=user_id, input=user_input)
    result = await orchestrator.run(request)

    print("\n" + "=" * 60)
    print(f"任务 ID : {result.task_id}")
    print(f"状态    : {result.status.value}")
    print(f"轮数    : {result.rounds_used}")
    if result.answer:
        print(f"回答    : {result.answer}")
    if result.error:
        print(f"错误    : {result.error}")
    print("=" * 60)

    print("\n── 审计日志 ──")
    for msg in result.messages:
        print(f"  [{msg.role.value}] r{msg.round_index}: {msg.content[:120]}")


def main() -> None:
    """CLI 入口：python -m herness.main "你的问题" """
    user_input = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "介绍一下 Herness Agent 框架的架构设计。"
    asyncio.run(run_demo(user_input))


if __name__ == "__main__":
    main()
