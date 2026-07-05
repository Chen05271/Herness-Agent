"""AgriCommerce 客户端工厂。"""

from __future__ import annotations

from typing import Literal

from herness.config import Settings
from herness.integrations.agri_commerce.http_client import HttpAgriCommerceClient
from herness.integrations.agri_commerce.mock_client import MockAgriCommerceClient
from herness.integrations.agri_commerce.protocol import AgriCommerceClient

AgriCommerceMode = Literal["mock", "http"]

# Worker 可调用的农业电商只读工具逻辑名
AGRI_COMMERCE_READ_TOOLS: frozenset[str] = frozenset(
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


def build_agri_commerce_client(settings: Settings) -> AgriCommerceClient | None:
    """按配置构建 BFF 客户端；未启用时返回 None。"""
    if not settings.agri_commerce_enabled:
        return None

    mode: AgriCommerceMode = settings.agri_commerce_mode
    if mode == "mock":
        return MockAgriCommerceClient()

    base_url = settings.agri_commerce_base_url.strip()
    if not base_url:
        raise ValueError(
            "AGRI_COMMERCE_MODE=http 时必须配置 AGRI_COMMERCE_BASE_URL"
        )

    return HttpAgriCommerceClient(
        base_url=base_url,
        api_key=settings.agri_commerce_api_key,
        timeout_seconds=settings.agri_commerce_timeout_seconds,
    )
