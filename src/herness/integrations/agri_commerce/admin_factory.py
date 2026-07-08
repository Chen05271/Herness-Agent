"""运营 BFF 客户端工厂。"""

from __future__ import annotations

from herness.config import Settings
from herness.integrations.agri_commerce.admin_http_client import HttpAgriAdminClient
from herness.integrations.agri_commerce.admin_mock_client import MockAgriAdminClient
from herness.integrations.agri_commerce.admin_protocol import AgriAdminClient

AGRI_ADMIN_TOOLS: frozenset[str] = frozenset(
    {
        "admin_get_dashboard",
        "admin_list_orders",
        "admin_get_order",
        "admin_list_products",
    }
)


def build_admin_commerce_client(
    settings: Settings,
    *,
    admin_token: str = "",
) -> AgriAdminClient | None:
    if not settings.agri_commerce_enabled:
        return None

    if settings.agri_commerce_mode == "mock":
        return MockAgriAdminClient()

    base_url = settings.agri_commerce_base_url.strip()
    if not base_url:
        return None

    token = admin_token or settings.agri_commerce_admin_token
    return HttpAgriAdminClient(
        base_url=base_url,
        admin_token=token,
        admin_api_key=settings.agri_commerce_api_key if not token else "",
        timeout_seconds=settings.agri_commerce_timeout_seconds,
    )
