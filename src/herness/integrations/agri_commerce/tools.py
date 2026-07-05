"""农业电商只读工具 — 供 Worker Agent 调用，返回 JSON 字符串。"""

from __future__ import annotations

import json
from typing import Any

from herness.integrations.agri_commerce.protocol import AgriCommerceClient, AgriCommerceError


def _dump(model: Any) -> str:
    if hasattr(model, "model_dump"):
        payload = model.model_dump(mode="json")
    else:
        payload = model
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _format_error(tool: str, exc: Exception) -> str:
    return f"{tool} 工具错误：{exc}"


async def tool_get_order(client: AgriCommerceClient, user_id: str, order_id: str) -> str:
    try:
        return _dump(await client.get_order(user_id, order_id))
    except AgriCommerceError as exc:
        return _format_error("get_order", exc)


async def tool_list_orders(
    client: AgriCommerceClient,
    user_id: str,
    *,
    status: str = "",
    limit: int = 10,
) -> str:
    try:
        return _dump(
            await client.list_orders(
                user_id,
                status=status or None,
                limit=limit,
            )
        )
    except AgriCommerceError as exc:
        return _format_error("list_orders", exc)


async def tool_get_order_timeline(
    client: AgriCommerceClient,
    user_id: str,
    order_id: str,
) -> str:
    try:
        return _dump(await client.get_order_timeline(user_id, order_id))
    except AgriCommerceError as exc:
        return _format_error("get_order_timeline", exc)


async def tool_get_lot(client: AgriCommerceClient, batch_id: str) -> str:
    try:
        return _dump(await client.get_lot(batch_id))
    except AgriCommerceError as exc:
        return _format_error("get_lot", exc)


async def tool_search_produce(
    client: AgriCommerceClient,
    *,
    q: str = "",
    category: str = "",
    region: str = "",
    limit: int = 10,
) -> str:
    try:
        return _dump(
            await client.search_produce(
                q=q,
                category=category,
                region=region,
                limit=limit,
            )
        )
    except AgriCommerceError as exc:
        return _format_error("search_produce", exc)


async def tool_get_availability(client: AgriCommerceClient, sku: str) -> str:
    try:
        return _dump(await client.get_availability(sku))
    except AgriCommerceError as exc:
        return _format_error("get_availability", exc)


async def tool_trace_batch(client: AgriCommerceClient, trace_id: str) -> str:
    try:
        return _dump(await client.trace_batch(trace_id))
    except AgriCommerceError as exc:
        return _format_error("trace_batch", exc)


async def tool_get_live_inventory_hint(
    client: AgriCommerceClient,
    room_id: str,
    *,
    q: str = "",
) -> str:
    try:
        return _dump(await client.get_live_inventory_hint(room_id, q=q))
    except AgriCommerceError as exc:
        return _format_error("get_live_inventory_hint", exc)
