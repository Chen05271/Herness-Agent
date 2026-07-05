"""Mock 果园样例数据 — 对接真实 API 前用于联调与测试。

替换方式：实现 HttpAgriCommerceClient 或扩展 MockAgriCommerceClient.load_from_json(path)。
"""

from __future__ import annotations

from datetime import datetime, timezone

from herness.integrations.agri_commerce.schemas import (
    AvailabilityInfo,
    LiveInventoryItem,
    LiveInventoryResponse,
    LotInfo,
    OrderListResponse,
    OrderSummary,
    OrderTimeline,
    ProductSearchHit,
    ProductSearchResponse,
    TimelineEvent,
    TraceRecord,
)

_DEMO_USER = "u-demo-001"

_ORDERS: dict[str, OrderSummary] = {
    "ORD-20260705-001": OrderSummary(
        order_id="ORD-20260705-001",
        user_id=_DEMO_USER,
        status="picking",
        sku="SKU-BB-80",
        sku_name="蓝莓 80+",
        trace_id="TRACE-20260705-a3",
        batch_id="LOT-A3-0714",
        amount_cny=128.0,
        estimated_pick_start=datetime(2026, 7, 5, 14, 30, tzinfo=timezone.utc),
        created_at=datetime(2026, 7, 5, 14, 10, tzinfo=timezone.utc),
    ),
    "ORD-20260704-002": OrderSummary(
        order_id="ORD-20260704-002",
        user_id=_DEMO_USER,
        status="delivered",
        sku="SKU-CH-1",
        sku_name="樱桃 一级果",
        trace_id="TRACE-20260704-b1",
        batch_id="LOT-B2-0703",
        amount_cny=89.0,
        estimated_pick_start=None,
        created_at=datetime(2026, 7, 4, 9, 0, tzinfo=timezone.utc),
    ),
}

_TIMELINES: dict[str, OrderTimeline] = {
    "ORD-20260705-001": OrderTimeline(
        order_id="ORD-20260705-001",
        trace_id="TRACE-20260705-a3",
        status="picking",
        events=[
            TimelineEvent(
                event_type="order_created",
                occurred_at=datetime(2026, 7, 5, 14, 10, tzinfo=timezone.utc),
                title="订单已创建",
                detail="C2F 模式：已预分配溯源 ID",
            ),
            TimelineEvent(
                event_type="pick_scheduled",
                occurred_at=datetime(2026, 7, 5, 14, 15, tzinfo=timezone.utc),
                title="待采摘",
                detail="预计 14:30 启动采摘机器人",
            ),
            TimelineEvent(
                event_type="picking",
                occurred_at=datetime(2026, 7, 5, 14, 28, tzinfo=timezone.utc),
                title="采摘中",
                detail="A 区 3 号树",
                robot_id="PICK-07",
                photo_url="https://cdn.example.com/pick/a3-0714.jpg",
            ),
        ],
    ),
}

_LOTS: dict[str, LotInfo] = {
    "LOT-A3-0714": LotInfo(
        batch_id="LOT-A3-0714",
        sku="SKU-BB-80",
        sku_name="蓝莓 80+",
        grade="一级",
        weight_g=218,
        brix=14.2,
        ph=6.2,
        harvest_zone="A 区 3 号树",
        harvested_at=datetime(2026, 7, 5, 14, 30, tzinfo=timezone.utc),
        robot_id="PICK-07",
    ),
}

_PRODUCTS: list[ProductSearchHit] = [
    ProductSearchHit(
        sku="SKU-BB-80",
        name="蓝莓 80+",
        region="胶东",
        grade="一级",
        price_cny=128.0,
        category="浆果",
    ),
    ProductSearchHit(
        sku="SKU-BB-70",
        name="蓝莓 70+",
        region="胶东",
        grade="二级",
        price_cny=98.0,
        category="浆果",
    ),
    ProductSearchHit(
        sku="SKU-CH-1",
        name="樱桃 一级果",
        region="烟台",
        grade="一级",
        price_cny=89.0,
        category="核果",
    ),
]

_AVAILABILITY: dict[str, AvailabilityInfo] = {
    "SKU-BB-80": AvailabilityInfo(
        sku="SKU-BB-80",
        sku_name="蓝莓 80+",
        available=True,
        c2f_mode=True,
        remaining_slots=12,
        estimated_pick_start=datetime(2026, 7, 5, 15, 0, tzinfo=timezone.utc),
        message="有人下单才采摘，预计 2 小时内启动",
    ),
    "SKU-BB-70": AvailabilityInfo(
        sku="SKU-BB-70",
        sku_name="蓝莓 70+",
        available=True,
        c2f_mode=True,
        remaining_slots=5,
        estimated_pick_start=datetime(2026, 7, 5, 16, 0, tzinfo=timezone.utc),
        message="剩余可接单量较少",
    ),
}

_TRACE: dict[str, TraceRecord] = {
    "TRACE-20260705-a3": TraceRecord(
        trace_id="TRACE-20260705-a3",
        order_id="ORD-20260705-001",
        batch_id="LOT-A3-0714",
        chain_hash="0xabc123def456",
        ipfs_cid="QmExampleCidA3",
        lot=_LOTS["LOT-A3-0714"],
        events=[
            TimelineEvent(
                event_type="picked",
                occurred_at=datetime(2026, 7, 5, 14, 30, tzinfo=timezone.utc),
                title="已采摘",
                detail="pH=6.2，糖度=14.2°Brix，重量=218g",
                robot_id="PICK-07",
            ),
            TimelineEvent(
                event_type="packed",
                occurred_at=datetime(2026, 7, 5, 15, 10, tzinfo=timezone.utc),
                title="已包装",
                detail="YOLO 分拣贴标完成",
            ),
            TimelineEvent(
                event_type="shipped",
                occurred_at=datetime(2026, 7, 5, 15, 25, tzinfo=timezone.utc),
                title="已发出",
                detail="抵达顺丰站点",
                logistics_no="SF1234567890",
            ),
        ],
    ),
}

_LIVE_INVENTORY: dict[str, list[LiveInventoryItem]] = {
    "live-room-01": [
        LiveInventoryItem(
            sku="SKU-BB-80",
            name="蓝莓 80+",
            available=True,
            remaining_slots=12,
            message="今日 A 区可采",
        ),
        LiveInventoryItem(
            sku="SKU-BB-70",
            name="蓝莓 70+",
            available=True,
            remaining_slots=5,
            message="",
        ),
    ],
}


def demo_user_id() -> str:
    return _DEMO_USER


def mock_orders_for_user(user_id: str) -> OrderListResponse:
    orders = [o for o in _ORDERS.values() if o.user_id == user_id]
    return OrderListResponse(orders=orders, total=len(orders))


def mock_order(user_id: str, order_id: str) -> OrderSummary | None:
    order = _ORDERS.get(order_id)
    if order is None or order.user_id != user_id:
        return None
    return order


def mock_timeline(user_id: str, order_id: str) -> OrderTimeline | None:
    if mock_order(user_id, order_id) is None:
        return None
    return _TIMELINES.get(order_id)


def mock_lot(batch_id: str) -> LotInfo | None:
    return _LOTS.get(batch_id)


def mock_search(q: str = "", category: str = "", region: str = "", limit: int = 10) -> ProductSearchResponse:
    items = _PRODUCTS
    if q:
        q_lower = q.lower()
        items = [
            p
            for p in items
            if q_lower in p.name.lower()
            or q_lower in p.sku.lower()
            or q in p.category
        ]
    if category:
        items = [p for p in items if category in p.category]
    if region:
        items = [p for p in items if region in p.region]
    items = items[:limit]
    return ProductSearchResponse(items=items, total=len(items))


def mock_availability(sku: str) -> AvailabilityInfo | None:
    return _AVAILABILITY.get(sku)


def mock_trace(trace_id: str) -> TraceRecord | None:
    return _TRACE.get(trace_id)


def mock_live_inventory(room_id: str, q: str = "") -> LiveInventoryResponse:
    items = list(_LIVE_INVENTORY.get(room_id, []))
    if q:
        q_lower = q.lower()
        items = [
            i
            for i in items
            if q_lower in i.name.lower() or q_lower in i.sku.lower()
        ]
    return LiveInventoryResponse(room_id=room_id, items=items, query=q)
