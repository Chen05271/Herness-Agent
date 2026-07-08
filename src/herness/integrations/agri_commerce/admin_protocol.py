"""运营后台 BFF 客户端协议。"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


class AgriAdminError(Exception):
    """运营 BFF 调用失败。"""


@runtime_checkable
class AgriAdminClient(Protocol):
    async def get_dashboard(self) -> dict[str, Any]:
        ...

    async def list_orders(
        self,
        *,
        status: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> dict[str, Any]:
        ...

    async def get_order(self, order_id: str) -> dict[str, Any]:
        ...

    async def list_products(self, *, limit: int = 20, offset: int = 0) -> dict[str, Any]:
        ...
