"""Critic Hereness 后校验单元测试。"""

import json

import pytest

from herness.agents.critic_validation import (
    apply_hereness_verification,
    apply_tool_verification,
)
from herness.middleware.stub import InMemoryMiddleware
from herness.models.critic import CriticOutput, FactCheckItem
from herness.models.worker import WorkerOutput, WorkerToolInvocation


@pytest.fixture
def hereness_mw() -> InMemoryMiddleware:
    return InMemoryMiddleware(hereness_enabled=True)


async def test_apply_hereness_rejects_contradiction(hereness_mw: InMemoryMiddleware) -> None:
    hereness_mw.seed_belief("u1", "用户不喜欢 Python", source="manual")
    output = CriticOutput(
        passed=True,
        feedback="",
        fact_checks=[],
        confidence=0.9,
    )
    worker_output = WorkerOutput(
        content="用户喜欢 Python 编程语言。",
        summary="介绍 Python",
        needs_verification=True,
    )

    verified = await apply_hereness_verification(
        output,
        middleware=hereness_mw,
        user_id="u1",
        worker_output=worker_output,
    )

    assert verified.passed is False
    assert any(item.status == "contradicted" for item in verified.fact_checks)
    assert verified.feedback


async def test_apply_hereness_supports_matching_claim(hereness_mw: InMemoryMiddleware) -> None:
    hereness_mw.seed_belief("u1", "用户偏好 Python 编程", source="dreaming")
    output = CriticOutput(passed=True, fact_checks=[], confidence=0.9)
    worker_output = WorkerOutput(
        content="用户喜欢 Python。",
        summary="Python 偏好",
        needs_verification=True,
    )

    verified = await apply_hereness_verification(
        output,
        middleware=hereness_mw,
        user_id="u1",
        worker_output=worker_output,
    )

    assert verified.passed is True
    assert any(item.status == "supported" for item in verified.fact_checks)


async def test_apply_hereness_checks_all_worker_claims_when_llm_partial(
    hereness_mw: InMemoryMiddleware,
) -> None:
    """LLM 只核查部分声明时，后校验仍应覆盖 Worker 正文中的其余声明。"""
    hereness_mw.seed_belief("u1", "用户不喜欢 Python", source="manual")
    output = CriticOutput(
        passed=True,
        feedback="",
        fact_checks=[
            FactCheckItem(claim="框架支持多 Agent 协作。", status="unknown", evidence=""),
        ],
        confidence=0.95,
    )
    worker_output = WorkerOutput(
        content="框架支持多 Agent 协作。用户喜欢 Python 编程语言。",
        summary="介绍框架",
        needs_verification=True,
    )

    verified = await apply_hereness_verification(
        output,
        middleware=hereness_mw,
        user_id="u1",
        worker_output=worker_output,
    )

    assert verified.passed is False
    claims = {item.claim for item in verified.fact_checks}
    assert "用户喜欢 Python 编程语言" in claims
    assert any(item.status == "contradicted" for item in verified.fact_checks)


async def test_apply_hereness_overrides_llm_supported_status(
    hereness_mw: InMemoryMiddleware,
) -> None:
    """信念库结果优先于 LLM 自报的 supported 状态。"""
    hereness_mw.seed_belief("u1", "用户不喜欢 Python", source="manual")
    output = CriticOutput(
        passed=True,
        fact_checks=[
            FactCheckItem(claim="用户喜欢 Python", status="supported", evidence="LLM 误判"),
        ],
        confidence=0.9,
    )
    worker_output = WorkerOutput(
        content="用户喜欢 Python。",
        summary="Python",
        needs_verification=True,
    )

    verified = await apply_hereness_verification(
        output,
        middleware=hereness_mw,
        user_id="u1",
        worker_output=worker_output,
    )

    assert verified.passed is False
    assert verified.fact_checks[0].status == "contradicted"


def test_apply_tool_verification_accepts_empty_list_orders_when_acknowledged() -> None:
    empty_orders = json.dumps({"orders": [], "total": 0}, ensure_ascii=False)
    output = CriticOutput(passed=True, feedback="", confidence=0.9)
    worker_output = WorkerOutput(
        content="根据 list_orders 查询，您今日暂无订单记录。",
        summary="list_orders 返回空列表，今日无订单",
        needs_verification=True,
        tool_invocations=[
            WorkerToolInvocation(
                tool_name="list_orders",
                result=empty_orders,
                error=False,
            )
        ],
    )

    verified = apply_tool_verification(output, worker_output)

    assert verified.passed is True
    assert verified.tool_checks[0].status == "ok"


def test_apply_tool_verification_rejects_nonempty_without_citation() -> None:
    orders = json.dumps(
        {
            "orders": [{"order_id": "ORD-20260705-001", "status": "picking"}],
            "total": 1,
        },
        ensure_ascii=False,
    )
    output = CriticOutput(passed=True, feedback="", confidence=0.9)
    worker_output = WorkerOutput(
        content="您有一笔订单正在处理中。",
        summary="查询订单",
        needs_verification=True,
        tool_invocations=[
            WorkerToolInvocation(
                tool_name="list_orders",
                result=orders,
                error=False,
            )
        ],
    )

    verified = apply_tool_verification(output, worker_output)

    assert verified.passed is False
    assert verified.tool_checks[0].status == "uncited"
    assert "list_orders" in verified.feedback
