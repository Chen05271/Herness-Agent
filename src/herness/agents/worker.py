"""执行 Agent — 只读权限，不可见全局记忆，仅接收任务指令。"""

from dataclasses import dataclass
from typing import Any

import httpx
from pydantic_ai import Agent, RunContext

from herness.agents.base import build_model
from herness.agents.tools import WorkerToolError, http_request, read_text_file, run_python_code
from herness.config import Settings
from herness.integrations.agri_commerce.protocol import AgriCommerceClient
from herness.integrations.agri_commerce.admin_protocol import AgriAdminClient
from herness.integrations.agri_commerce import tools as agri_tools
from herness.integrations.agri_commerce import admin_tools as agri_admin_tools
from herness.middleware.protocol import ReadOnlyMiddleware
from herness.models.worker import WORKER_KINDS, WorkerKind, WorkerOutput
from herness.personas import Persona
from herness.rag.collections import resolve_kb_collection
from herness.rag.tools import format_rag_context

_DEFAULT_WORKER_SYSTEM = """\
你是 Herness 系统的执行 Agent（Worker）。
职责：
1. 根据总管给出的任务指令完成具体工作
2. 输出结构化结果，包含 content、summary

限制：
- 你看不到全局记忆，只能使用任务指令与局部上下文
- 不要尝试规划或校验，专注执行
- 完成后设置 needs_verification=true（除非任务明确无需校验）

可用工具（若已启用）：fetch_task_context、http_request、read_text_file、run_python_code、search_knowledge_base。
使用工具时请在 content 中引用关键结果；涉及外部数据时务必标注来源。
"""


@dataclass
class WorkerDeps:
    """执行 Agent 依赖 — 仅只读中台，无全局记忆。"""

    middleware: ReadOnlyMiddleware
    user_id: str
    task_id: str
    local_context: dict[str, Any]
    allowed_tools: frozenset[str]
    worker_type: WorkerKind = "default"
    persona: Persona = "consumer"
    agri_client: AgriCommerceClient | None = None
    admin_client: AgriAdminClient | None = None


def _tool_denied(tool_name: str) -> str:
    return f"{tool_name} 工具错误：当前任务未授权使用该工具"


def _register_worker_tools(
    agent: Agent[WorkerDeps, WorkerOutput],
    settings: Settings,
) -> None:
    """按 Settings 向 Worker Agent 注册外部工具。"""
    if settings.worker_tools_http_enabled:

        @agent.tool
        async def http_request_tool(
            ctx: RunContext[WorkerDeps],
            url: str,
            method: str = "GET",
            body: str | None = None,
        ) -> str:
            """发起 HTTP/HTTPS 请求并返回响应文本。method 支持 GET/POST/PUT/PATCH/DELETE。"""
            if "http_request" not in ctx.deps.allowed_tools:
                return _tool_denied("http_request")
            try:
                return await http_request(url, method=method, body=body, settings=settings)
            except WorkerToolError as exc:
                return f"HTTP 工具错误：{exc}"
            except httpx.HTTPError as exc:
                return f"HTTP 请求失败：{type(exc).__name__}: {exc}"

    file_enabled = (
        settings.worker_tools_file_enabled
        and bool(settings.worker_tools_file_base_dir.strip())
    )
    if file_enabled:

        @agent.tool
        async def read_text_file_tool(ctx: RunContext[WorkerDeps], path: str) -> str:
            """读取 WORKER_TOOLS_FILE_BASE_DIR 内的文本文件。"""
            if "read_text_file" not in ctx.deps.allowed_tools:
                return _tool_denied("read_text_file")
            try:
                return await read_text_file(path, settings=settings)
            except WorkerToolError as exc:
                return f"文件工具错误：{exc}"

    if settings.worker_tools_code_enabled:

        @agent.tool
        async def run_python_code_tool(ctx: RunContext[WorkerDeps], code: str) -> str:
            """在隔离子进程中执行 Python 代码片段，返回 stdout/stderr 与 exit_code。"""
            if "run_python_code" not in ctx.deps.allowed_tools:
                return _tool_denied("run_python_code")
            try:
                return await run_python_code(code, settings=settings)
            except WorkerToolError as exc:
                return f"代码执行错误：{exc}"


def _register_rag_tools(
    agent: Agent[WorkerDeps, WorkerOutput],
    settings: Settings,
) -> None:
    if not settings.rag_enabled:
        return

    @agent.tool
    async def search_knowledge_base(
        ctx: RunContext[WorkerDeps],
        query: str,
        collection: str = "",
    ) -> str:
        """检索领域 RAG 知识库（粗检索 → 细检索 → Re-rank），返回相关文档片段。"""
        if "search_knowledge_base" not in ctx.deps.allowed_tools:
            return _tool_denied("search_knowledge_base")
        collection_id = resolve_kb_collection(ctx.deps.persona, collection=collection or None)
        result = await ctx.deps.middleware.search_knowledge_base(
            query,
            collection_id=collection_id,
            user_id=ctx.deps.user_id,
        )
        return format_rag_context(result)


def _register_agri_commerce_tools(
    agent: Agent[WorkerDeps, WorkerOutput],
    settings: Settings,
) -> None:
    """注册农业电商只读 BFF 工具（需 AGRI_COMMERCE_ENABLED=true）。"""
    if not settings.agri_commerce_enabled:
        return

    @agent.tool
    async def get_order(ctx: RunContext[WorkerDeps], order_id: str) -> str:
        """查询订单详情（状态、SKU、溯源 ID、预计采摘时间）。"""
        if "get_order" not in ctx.deps.allowed_tools:
            return _tool_denied("get_order")
        if ctx.deps.agri_client is None:
            return "get_order 工具错误：农业电商 BFF 未配置"
        return await agri_tools.tool_get_order(
            ctx.deps.agri_client, ctx.deps.user_id, order_id
        )

    @agent.tool
    async def list_orders(
        ctx: RunContext[WorkerDeps],
        status: str = "",
        limit: int = 10,
    ) -> str:
        """列出用户近期订单，可按 status 过滤。"""
        if "list_orders" not in ctx.deps.allowed_tools:
            return _tool_denied("list_orders")
        if ctx.deps.agri_client is None:
            return "list_orders 工具错误：农业电商 BFF 未配置"
        return await agri_tools.tool_list_orders(
            ctx.deps.agri_client, ctx.deps.user_id, status=status, limit=limit
        )

    @agent.tool
    async def get_order_timeline(ctx: RunContext[WorkerDeps], order_id: str) -> str:
        """查询订单 C2F 全链路时间线（待采摘→签收）。"""
        if "get_order_timeline" not in ctx.deps.allowed_tools:
            return _tool_denied("get_order_timeline")
        if ctx.deps.agri_client is None:
            return "get_order_timeline 工具错误：农业电商 BFF 未配置"
        return await agri_tools.tool_get_order_timeline(
            ctx.deps.agri_client, ctx.deps.user_id, order_id
        )

    @agent.tool
    async def get_lot(ctx: RunContext[WorkerDeps], batch_id: str) -> str:
        """查询批次质检信息（等级、糖度、pH、重量、采收区）。"""
        if "get_lot" not in ctx.deps.allowed_tools:
            return _tool_denied("get_lot")
        if ctx.deps.agri_client is None:
            return "get_lot 工具错误：农业电商 BFF 未配置"
        return await agri_tools.tool_get_lot(ctx.deps.agri_client, batch_id)

    @agent.tool
    async def search_produce(
        ctx: RunContext[WorkerDeps],
        q: str = "",
        category: str = "",
        region: str = "",
        limit: int = 10,
    ) -> str:
        """搜索可售农产品。"""
        if "search_produce" not in ctx.deps.allowed_tools:
            return _tool_denied("search_produce")
        if ctx.deps.agri_client is None:
            return "search_produce 工具错误：农业电商 BFF 未配置"
        return await agri_tools.tool_search_produce(
            ctx.deps.agri_client, q=q, category=category, region=region, limit=limit
        )

    @agent.tool
    async def get_availability(ctx: RunContext[WorkerDeps], sku: str) -> str:
        """查询 SKU 的 C2F 可售量与预计采摘窗口。"""
        if "get_availability" not in ctx.deps.allowed_tools:
            return _tool_denied("get_availability")
        if ctx.deps.agri_client is None:
            return "get_availability 工具错误：农业电商 BFF 未配置"
        return await agri_tools.tool_get_availability(ctx.deps.agri_client, sku)

    @agent.tool
    async def trace_batch(ctx: RunContext[WorkerDeps], trace_id: str) -> str:
        """查询溯源聚合记录（链哈希、IPFS、生命周期事件）。"""
        if "trace_batch" not in ctx.deps.allowed_tools:
            return _tool_denied("trace_batch")
        if ctx.deps.agri_client is None:
            return "trace_batch 工具错误：农业电商 BFF 未配置"
        return await agri_tools.tool_trace_batch(ctx.deps.agri_client, trace_id)

    @agent.tool
    async def get_live_inventory_hint(
        ctx: RunContext[WorkerDeps],
        room_id: str,
        q: str = "",
    ) -> str:
        """查询直播间可售库存快照（如「今天有蓝莓吗」）。"""
        if "get_live_inventory_hint" not in ctx.deps.allowed_tools:
            return _tool_denied("get_live_inventory_hint")
        if ctx.deps.agri_client is None:
            return "get_live_inventory_hint 工具错误：农业电商 BFF 未配置"
        return await agri_tools.tool_get_live_inventory_hint(
            ctx.deps.agri_client, room_id, q=q
        )


def _register_agri_admin_tools(agent: Agent[WorkerDeps, WorkerOutput]) -> None:
    @agent.tool
    async def admin_get_dashboard(ctx: RunContext[WorkerDeps]) -> str:
        """查询运营仪表盘汇总（订单量、待采摘、在售 SKU 等）。"""
        if "admin_get_dashboard" not in ctx.deps.allowed_tools:
            return _tool_denied("admin_get_dashboard")
        if ctx.deps.admin_client is None:
            return "admin_get_dashboard 工具错误：运营 BFF 未配置"
        return await agri_admin_tools.tool_admin_get_dashboard(ctx.deps.admin_client)

    @agent.tool
    async def admin_list_orders(
        ctx: RunContext[WorkerDeps],
        status: str = "",
        limit: int = 20,
    ) -> str:
        """列出平台订单（运营视角，可按状态筛选）。"""
        if "admin_list_orders" not in ctx.deps.allowed_tools:
            return _tool_denied("admin_list_orders")
        if ctx.deps.admin_client is None:
            return "admin_list_orders 工具错误：运营 BFF 未配置"
        return await agri_admin_tools.tool_admin_list_orders(
            ctx.deps.admin_client, status=status, limit=limit
        )

    @agent.tool
    async def admin_get_order(ctx: RunContext[WorkerDeps], order_id: str) -> str:
        """查询单笔订单详情（运营视角）。"""
        if "admin_get_order" not in ctx.deps.allowed_tools:
            return _tool_denied("admin_get_order")
        if ctx.deps.admin_client is None:
            return "admin_get_order 工具错误：运营 BFF 未配置"
        return await agri_admin_tools.tool_admin_get_order(ctx.deps.admin_client, order_id)

    @agent.tool
    async def admin_list_products(ctx: RunContext[WorkerDeps], limit: int = 20) -> str:
        """列出全部 SKU 及上下架状态。"""
        if "admin_list_products" not in ctx.deps.allowed_tools:
            return _tool_denied("admin_list_products")
        if ctx.deps.admin_client is None:
            return "admin_list_products 工具错误：运营 BFF 未配置"
        return await agri_admin_tools.tool_admin_list_products(
            ctx.deps.admin_client, limit=limit
        )


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
        if "fetch_task_context" not in ctx.deps.allowed_tools:
            return _tool_denied("fetch_task_context")
        context = await ctx.deps.middleware.get_task_context(
            ctx.deps.user_id, ctx.deps.task_id
        )
        return str(context)

    _register_worker_tools(agent, settings)
    _register_rag_tools(agent, settings)
    _register_agri_commerce_tools(agent, settings)
    _register_agri_admin_tools(agent)

    return agent
