"""In-memory Mock BFF — 开发/测试用，数据见 mock_data.py。"""

from __future__ import annotations

from herness.integrations.agri_commerce import mock_data
from herness.integrations.agri_commerce.protocol import AgriCommerceError
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


class MockAgriCommerceClient:
    """本地 mock 客户端；后续可 load_from_json 注入真实果园快照。"""

    async def get_order(self, user_id: str, order_id: str) -> OrderSummary:
        order = mock_data.mock_order(user_id, order_id)
        if order is None:
            raise AgriCommerceError(f"订单不存在或无权访问：{order_id!r}")
        return order

    async def list_orders(
        self,
        user_id: str,
        *,
        status: str | None = None,
        limit: int = 10,
    ) -> OrderListResponse:
        result = mock_data.mock_orders_for_user(user_id)
        orders = result.orders
        if status:
            orders = [o for o in orders if o.status == status]
        orders = orders[:limit]
        return OrderListResponse(orders=orders, total=len(orders))

    async def get_order_timeline(self, user_id: str, order_id: str) -> OrderTimeline:
        timeline = mock_data.mock_timeline(user_id, order_id)
        if timeline is None:
            raise AgriCommerceError(f"订单时间线不存在：{order_id!r}")
        return timeline

    async def get_lot(self, batch_id: str) -> LotInfo:
        lot = mock_data.mock_lot(batch_id)
        if lot is None:
            raise AgriCommerceError(f"批次不存在：{batch_id!r}")
        return lot

    async def search_produce(
        self,
        *,
        q: str = "",
        category: str = "",
        region: str = "",
        limit: int = 10,
    ) -> ProductSearchResponse:
        return mock_data.mock_search(q=q, category=category, region=region, limit=limit)

    async def get_availability(self, sku: str) -> AvailabilityInfo:
        info = mock_data.mock_availability(sku)
        if info is None:
            raise AgriCommerceError(f"SKU 不存在：{sku!r}")
        return info

    async def trace_batch(self, trace_id: str) -> TraceRecord:
        record = mock_data.mock_trace(trace_id)
        if record is None:
            raise AgriCommerceError(f"溯源记录不存在：{trace_id!r}")
        return record

    async def get_live_inventory_hint(
        self,
        room_id: str,
        *,
        q: str = "",
    ) -> LiveInventoryResponse:
        return mock_data.mock_live_inventory(room_id, q=q)
