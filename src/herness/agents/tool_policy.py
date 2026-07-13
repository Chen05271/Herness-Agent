"""Worker 工具权限策略 — 全局 Settings + 中台 + 任务 metadata 三层交集。"""

from __future__ import annotations

from typing import Any

from herness.config import Settings
from herness.integrations.agri_commerce.factory import AGRI_COMMERCE_READ_TOOLS
from herness.integrations.agri_commerce.admin_factory import AGRI_ADMIN_TOOLS
from herness.middleware.protocol import ReadOnlyMiddleware

ALL_WORKER_TOOLS: frozenset[str] = frozenset(
    {
        "fetch_task_context",
        "http_request",
        "http_request_tool",
        "read_text_file",
        "read_text_file_tool",
        "run_python_code",
        "run_python_code_tool",
        "ppt_master_build_pptx",
        "ppt_master_build_pptx_tool",
        "ppt_master_export_project",
        "ppt_master_export_project_tool",
        "ppt_master_export_svg_to_pptx",
        "ppt_master_export_svg_to_pptx_tool",
    }
)

# pydantic-ai 注册名 → 逻辑名
_TOOL_ALIASES: dict[str, str] = {
    "http_request_tool": "http_request",
    "read_text_file_tool": "read_text_file",
    "run_python_code_tool": "run_python_code",
    "ppt_master_build_pptx_tool": "ppt_master_build_pptx",
    "ppt_master_export_project_tool": "ppt_master_export_project",
    "ppt_master_export_svg_to_pptx_tool": "ppt_master_export_svg_to_pptx",
}


def normalize_tool_name(name: str) -> str:
    return _TOOL_ALIASES.get(name, name)


def globally_enabled_tools(settings: Settings) -> set[str]:
    """根据全局配置返回可用工具逻辑名。"""
    enabled = {"fetch_task_context"}
    if settings.worker_tools_http_enabled:
        enabled.add("http_request")
    if settings.worker_tools_file_enabled and settings.worker_tools_file_base_dir.strip():
        enabled.add("read_text_file")
    if settings.worker_tools_code_enabled:
        enabled.add("run_python_code")
    if settings.worker_tools_ppt_enabled and settings.worker_tools_output_base_dir.strip():
        enabled.add("ppt_master_build_pptx")
        enabled.add("ppt_master_export_project")
        enabled.add("ppt_master_export_svg_to_pptx")
    if settings.agri_commerce_enabled:
        enabled |= set(AGRI_COMMERCE_READ_TOOLS)
        enabled |= set(AGRI_ADMIN_TOOLS)
    return enabled


def _metadata_tool_names(metadata: dict[str, Any], key: str) -> set[str] | None:
    raw = metadata.get(key)
    if raw is None:
        return None
    if not isinstance(raw, list):
        return None
    return {normalize_tool_name(str(item)) for item in raw}


async def resolve_allowed_worker_tools(
    settings: Settings,
    middleware: ReadOnlyMiddleware,
    *,
    user_id: str,
    task_id: str,
    metadata: dict[str, Any] | None = None,
) -> set[str]:
    """解析任务级允许工具：全局开关 ∩ 中台策略 ∩ metadata 白/黑名单。"""
    allowed = globally_enabled_tools(settings)

    resolver = getattr(middleware, "resolve_worker_tools", None)
    if resolver is not None:
        mw_tools = await resolver(user_id, task_id)
        if mw_tools is not None:
            allowed &= {normalize_tool_name(name) for name in mw_tools}

    meta = metadata or {}
    whitelist = _metadata_tool_names(meta, "allowed_tools")
    if whitelist is not None:
        allowed &= whitelist

    denied = _metadata_tool_names(meta, "denied_tools")
    if denied is not None:
        allowed -= denied

    return allowed
