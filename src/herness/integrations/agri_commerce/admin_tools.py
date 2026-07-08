"""运营后台只读工具 — 供 merchant persona Worker 调用。"""

from __future__ import annotations

import json
from typing import Any

from herness.integrations.agri_commerce.admin_protocol import AgriAdminClient, AgriAdminError


def _dump(model: Any) -> str:
    return json.dumps(model, ensure_ascii=False, indent=2)


def _format_error(tool: str, exc: Exception) -> str:
    return f"{tool} 工具错误：{exc}"


async def tool_admin_get_dashboard(client: AgriAdminClient) -> str:
    try:
        return _dump(await client.get_dashboard())
    except AgriAdminError as exc:
        return _format_error("admin_get_dashboard", exc)


async def tool_admin_list_orders(
    client: AgriAdminClient,
    *,
    status: str = "",
    limit: int = 20,
) -> str:
    try:
        return _dump(
            await client.list_orders(
                status=status or None,
                limit=limit,
            )
        )
    except AgriAdminError as exc:
        return _format_error("admin_list_orders", exc)


async def tool_admin_get_order(client: AgriAdminClient, order_id: str) -> str:
    try:
        return _dump(await client.get_order(order_id))
    except AgriAdminError as exc:
        return _format_error("admin_get_order", exc)


async def tool_admin_list_products(client: AgriAdminClient, *, limit: int = 20) -> str:
    try:
        return _dump(await client.list_products(limit=limit))
    except AgriAdminError as exc:
        return _format_error("admin_list_products", exc)
