"""HTTP BFF 客户端 — 对接 openapi.yaml 定义的真实果园电商 API。"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlencode

import httpx

from herness.integrations.agri_commerce.protocol import AgriCommerceError
from herness.integrations.agri_commerce.schemas import (
    AvailabilityInfo,
    ErrorResponse,
    LiveInventoryResponse,
    LotInfo,
    OrderListResponse,
    OrderSummary,
    OrderTimeline,
    ProductSearchResponse,
    TraceRecord,
)


class HttpAgriCommerceClient:
    """只读 HTTP 客户端；Base URL 指向电商 BFF，非 Kafka/ROS2。"""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str = "",
        timeout_seconds: float = 30.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._timeout = timeout_seconds

    def _headers(self, user_id: str | None = None) -> dict[str, str]:
        headers: dict[str, str] = {"Accept": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        if user_id:
            headers["X-User-Id"] = user_id
        return headers

    async def _request(
        self,
        method: str,
        path: str,
        *,
        user_id: str | None = None,
        params: dict[str, Any] | None = None,
    ) -> Any:
        url = f"{self._base_url}{path}"
        if params:
            query = urlencode({k: v for k, v in params.items() if v not in (None, "")})
            if query:
                url = f"{url}?{query}"

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            try:
                response = await client.request(
                    method,
                    url,
                    headers=self._headers(user_id),
                )
            except httpx.HTTPError as exc:
                raise AgriCommerceError(f"HTTP 请求失败：{exc}") from exc

        if response.status_code >= 400:
            message = response.text
            try:
                err = ErrorResponse.model_validate_json(response.text)
                message = err.error
            except Exception:
                pass
            raise AgriCommerceError(f"BFF 错误 {response.status_code}：{message}")

        return response.json()

    async def get_order(self, user_id: str, order_id: str) -> OrderSummary:
        data = await self._request("GET", f"/v1/orders/{order_id}", user_id=user_id)
        return OrderSummary.model_validate(data)

    async def list_orders(
        self,
        user_id: str,
        *,
        status: str | None = None,
        limit: int = 10,
    ) -> OrderListResponse:
        data = await self._request(
            "GET",
            "/v1/orders",
            user_id=user_id,
            params={"status": status, "limit": limit},
        )
        return OrderListResponse.model_validate(data)

    async def get_order_timeline(self, user_id: str, order_id: str) -> OrderTimeline:
        data = await self._request(
            "GET",
            f"/v1/orders/{order_id}/timeline",
            user_id=user_id,
        )
        return OrderTimeline.model_validate(data)

    async def get_lot(self, batch_id: str) -> LotInfo:
        data = await self._request("GET", f"/v1/lots/{batch_id}")
        return LotInfo.model_validate(data)

    async def search_produce(
        self,
        *,
        q: str = "",
        category: str = "",
        region: str = "",
        limit: int = 10,
    ) -> ProductSearchResponse:
        data = await self._request(
            "GET",
            "/v1/products/search",
            params={"q": q, "category": category, "region": region, "limit": limit},
        )
        return ProductSearchResponse.model_validate(data)

    async def get_availability(self, sku: str) -> AvailabilityInfo:
        data = await self._request("GET", f"/v1/products/{sku}/availability")
        return AvailabilityInfo.model_validate(data)

    async def trace_batch(self, trace_id: str) -> TraceRecord:
        data = await self._request("GET", f"/v1/trace/{trace_id}")
        return TraceRecord.model_validate(data)

    async def get_live_inventory_hint(
        self,
        room_id: str,
        *,
        q: str = "",
    ) -> LiveInventoryResponse:
        data = await self._request(
            "GET",
            f"/v1/live/{room_id}/inventory",
            params={"q": q},
        )
        return LiveInventoryResponse.model_validate(data)
