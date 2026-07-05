"""AgriCommerce BFF 客户端协议 — mock 与 HTTP 实现共用。"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from herness.integrations.agri_commerce.schemas import (
    AvailabilityInfo,
    LiveInventoryResponse,
    LotInfo,
    OrderListResponse,
    OrderSummary,
    OrderTimeline,
    ProductSearchResponse,
    TraceRecord,
)


class AgriCommerceError(Exception):
    """BFF 调用失败（404、鉴权、网络等）。"""


@runtime_checkable
class AgriCommerceClient(Protocol):
    """智慧农业电商只读 BFF — 农场调度链路由电商平台聚合，Herness 不直连 ROS/链节点。"""

    async def get_order(self, user_id: str, order_id: str) -> OrderSummary:
        ...

    async def list_orders(
        self,
        user_id: str,
        *,
        status: str | None = None,
        limit: int = 10,
    ) -> OrderListResponse:
        ...

    async def get_order_timeline(self, user_id: str, order_id: str) -> OrderTimeline:
        ...

    async def get_lot(self, batch_id: str) -> LotInfo:
        ...

    async def search_produce(
        self,
        *,
        q: str = "",
        category: str = "",
        region: str = "",
        limit: int = 10,
    ) -> ProductSearchResponse:
        ...

    async def get_availability(self, sku: str) -> AvailabilityInfo:
        ...

    async def trace_batch(self, trace_id: str) -> TraceRecord:
        ...

    async def get_live_inventory_hint(
        self,
        room_id: str,
        *,
        q: str = "",
    ) -> LiveInventoryResponse:
        ...
