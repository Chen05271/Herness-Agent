"""运营后台 HTTP 客户端 — 对接 Spring Boot /admin/*。"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlencode

import httpx

from herness.integrations.agri_commerce.admin_protocol import AgriAdminError


class HttpAgriAdminClient:
    def __init__(
        self,
        *,
        base_url: str,
        admin_token: str = "",
        admin_api_key: str = "",
        timeout_seconds: float = 30.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._admin_token = admin_token
        self._admin_api_key = admin_api_key
        self._timeout = timeout_seconds

    def _headers(self) -> dict[str, str]:
        headers: dict[str, str] = {"Accept": "application/json"}
        if self._admin_token:
            headers["Authorization"] = f"Bearer {self._admin_token}"
        elif self._admin_api_key:
            headers["X-Admin-Key"] = self._admin_api_key
        return headers

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
    ) -> Any:
        url = f"{self._base_url}{path}"
        if params:
            query = urlencode({k: v for k, v in params.items() if v not in (None, "")})
            if query:
                url = f"{url}?{query}"

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            try:
                response = await client.request(method, url, headers=self._headers())
            except httpx.HTTPError as exc:
                raise AgriAdminError(f"HTTP 请求失败：{exc}") from exc

        if response.status_code >= 400:
            message = response.text
            try:
                payload = response.json()
                if isinstance(payload, dict):
                    message = payload.get("message") or payload.get("error") or message
            except Exception:
                pass
            raise AgriAdminError(f"运营 API 错误 {response.status_code}：{message}")

        body = response.json()
        if isinstance(body, dict) and "code" in body and "data" in body:
            if body.get("code") != 200:
                raise AgriAdminError(body.get("message") or "运营 API 返回失败")
            return body["data"]
        return body

    async def get_dashboard(self) -> dict[str, Any]:
        return await self._request("GET", "/admin/dashboard")

    async def list_orders(
        self,
        *,
        status: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> dict[str, Any]:
        return await self._request(
            "GET",
            "/admin/orders",
            params={"status": status, "limit": limit, "offset": offset},
        )

    async def get_order(self, order_id: str) -> dict[str, Any]:
        return await self._request("GET", f"/admin/orders/{order_id}")

    async def list_products(self, *, limit: int = 20, offset: int = 0) -> dict[str, Any]:
        return await self._request(
            "GET",
            "/admin/products",
            params={"limit": limit, "offset": offset},
        )
