"""C 端 / B 端 persona 工具白名单与 Supervisor 提示词。"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any, Literal

from herness.models.task import TaskRequest

if TYPE_CHECKING:
    from herness.config import Settings

Persona = Literal["consumer", "merchant"]

# 可选领域集成工具（如 AGRI_COMMERCE_ENABLED=true 时注入）
CONSUMER_DOMAIN_TOOLS: frozenset[str] = frozenset(
    {
        "get_order",
        "list_orders",
        "get_order_timeline",
        "get_lot",
        "search_produce",
        "get_availability",
        "trace_batch",
        "get_live_inventory_hint",
    }
)

MERCHANT_DOMAIN_TOOLS: frozenset[str] = frozenset(
    {
        "admin_get_dashboard",
        "admin_list_orders",
        "admin_get_order",
        "admin_list_products",
    }
)

_BASE_TOOLS: frozenset[str] = frozenset({"fetch_task_context"})

RAG_TOOLS: frozenset[str] = frozenset({"search_knowledge_base"})

_MERCHANT_USER_ID_RE = re.compile(r"^merchant:[^:]+:ops:[^:]+$")

_MERCHANT_SESSION_PREFIXES = ("admin-", "merchant-")
_CONSUMER_SESSION_PREFIX = "consumer-"


class PersonaValidationError(ValueError):
    """user_id / session_id 与 persona 不匹配。"""


def get_persona(metadata: dict[str, Any] | None) -> Persona:
    value = (metadata or {}).get("persona", "consumer")
    return "merchant" if value == "merchant" else "consumer"


def is_merchant_user_id(user_id: str) -> bool:
    """判断 user_id 是否属于商家运营命名空间。"""
    return bool(_MERCHANT_USER_ID_RE.match(user_id.strip()))


def validate_persona_identity(user_id: str, persona: Persona) -> None:
    """校验 user_id 与 persona 一致，防止记忆与工具越权。"""
    normalized = user_id.strip()
    if not normalized:
        raise PersonaValidationError("user_id 不能为空")

    if persona == "merchant":
        if not is_merchant_user_id(normalized):
            raise PersonaValidationError(
                "merchant persona 要求 user_id 格式为 merchant:{merchant_id}:ops:{operator_id}"
            )
        return

    if is_merchant_user_id(normalized):
        raise PersonaValidationError("consumer persona 禁止使用 merchant 命名空间的 user_id")


def default_session_id(persona: Persona, user_id: str) -> str:
    """按 persona 生成默认 session_id。"""
    if persona == "merchant":
        return f"admin-{user_id}"
    return f"{_CONSUMER_SESSION_PREFIX}{user_id}"


def normalize_session_id(persona: Persona, user_id: str, session_id: str) -> str:
    """为 session 注入 persona 命名空间，避免 C/B 端会话串线。"""
    sid = (session_id or "").strip()
    normalized_user = user_id.strip()

    if persona == "merchant":
        if sid.startswith(_CONSUMER_SESSION_PREFIX):
            raise PersonaValidationError("merchant persona 禁止使用 consumer session 命名空间")
        if not sid:
            return default_session_id(persona, normalized_user)
        if sid.startswith(_MERCHANT_SESSION_PREFIXES):
            return sid
        return f"admin-{normalized_user}:{sid}"

    if sid.startswith(_MERCHANT_SESSION_PREFIXES):
        raise PersonaValidationError("consumer persona 禁止使用商家 session 命名空间")
    if not sid:
        return default_session_id(persona, normalized_user)
    if sid.startswith(_CONSUMER_SESSION_PREFIX):
        return sid
    return f"{_CONSUMER_SESSION_PREFIX}{normalized_user}:{sid}"


def prepare_task_request(
    request: TaskRequest,
    *,
    settings: Settings | None = None,
) -> TaskRequest:
    """规范化任务请求：注入 persona 白名单、校验身份、隔离 session。"""
    meta = enrich_metadata_with_persona(request.metadata, settings=settings)
    persona = get_persona(meta)
    validate_persona_identity(request.user_id, persona)
    session_id = normalize_session_id(persona, request.user_id, request.session_id)
    return request.model_copy(update={"metadata": meta, "session_id": session_id})


def default_allowed_tools(
    persona: Persona,
    *,
    domain_tools_enabled: bool = False,
    rag_enabled: bool = False,
) -> list[str]:
    tools = set(_BASE_TOOLS)
    if rag_enabled:
        tools |= RAG_TOOLS
    if domain_tools_enabled:
        if persona == "merchant":
            tools |= MERCHANT_DOMAIN_TOOLS
        else:
            tools |= CONSUMER_DOMAIN_TOOLS
    return sorted(tools)


def enrich_metadata_with_persona(
    metadata: dict[str, Any] | None,
    *,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """按 persona 注入默认工具白名单（不覆盖调用方显式传入的 allowed_tools）。"""
    meta = dict(metadata or {})
    persona = get_persona(meta)
    meta["persona"] = persona
    if "allowed_tools" not in meta:
        domain_enabled = bool(settings and settings.agri_commerce_enabled)
        rag_enabled = bool(settings and settings.rag_enabled)
        meta["allowed_tools"] = default_allowed_tools(
            persona,
            domain_tools_enabled=domain_enabled,
            rag_enabled=rag_enabled,
        )
    return meta


def supervisor_persona_block(persona: Persona) -> str:
    if persona == "merchant":
        return (
            "## 当前角色：管理端助手\n"
            "- 服务对象：后台操作员\n"
            "- 重点：运营数据查询、业务指标、管理类操作\n"
            "- 禁止冒充终端用户或访问用户私有数据\n"
        )
    return (
        "## 当前角色：用户端助手\n"
        "- 服务对象：终端用户\n"
        "- 重点：理解用户需求、查询用户可见信息、给出清晰回答\n"
        "- 禁止访问管理端接口或越权数据\n"
    )


def supervisor_domain_block(settings: Settings) -> str:
    """可选领域集成路由提示；未启用集成时返回空字符串。"""
    if not settings.agri_commerce_enabled:
        return ""
    return (
        "## 领域集成（农业电商）\n"
        "- 订单/物流 → order_ops Worker\n"
        "- 商品/库存 → product Worker\n"
        "- 溯源/质检 → traceability Worker\n"
    )


def agent_user_id(persona: Persona, *, consumer_user_id: str, merchant_id: str, operator_id: str) -> str:
    """Herness 记忆隔离用的 agent user_id。"""
    if persona == "merchant":
        return f"merchant:{merchant_id}:ops:{operator_id}"
    return consumer_user_id
