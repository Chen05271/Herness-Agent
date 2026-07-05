"""智慧农业电商 BFF 数据模型 — 与 openapi.yaml 对齐。"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

OrderStatus = Literal[
    "pending_pick",
    "picking",
    "picked",
    "packed",
    "shipping",
    "delivered",
    "cancelled",
]

TimelineEventType = Literal[
    "order_created",
    "pick_scheduled",
    "picking",
    "picked",
    "packed",
    "shipped",
    "delivered",
]


class OrderSummary(BaseModel):
    order_id: str
    user_id: str
    status: OrderStatus
    sku: str
    sku_name: str
    trace_id: str
    batch_id: str | None = None
    amount_cny: float
    estimated_pick_start: datetime | None = None
    created_at: datetime


class OrderListResponse(BaseModel):
    orders: list[OrderSummary]
    total: int


class TimelineEvent(BaseModel):
    event_type: TimelineEventType
    occurred_at: datetime
    title: str
    detail: str = ""
    robot_id: str | None = None
    photo_url: str | None = None
    logistics_no: str | None = None


class OrderTimeline(BaseModel):
    order_id: str
    trace_id: str
    status: OrderStatus
    events: list[TimelineEvent]


class LotInfo(BaseModel):
    batch_id: str
    sku: str
    sku_name: str
    grade: str
    weight_g: int
    brix: float | None = None
    ph: float | None = None
    harvest_zone: str
    harvested_at: datetime | None = None
    robot_id: str | None = None


class ProductSearchHit(BaseModel):
    sku: str
    name: str
    region: str
    grade: str
    price_cny: float
    category: str


class ProductSearchResponse(BaseModel):
    items: list[ProductSearchHit]
    total: int


class AvailabilityInfo(BaseModel):
    sku: str
    sku_name: str
    available: bool
    c2f_mode: bool = True
    remaining_slots: int = 0
    estimated_pick_start: datetime | None = None
    message: str = ""


class TraceRecord(BaseModel):
    trace_id: str
    order_id: str
    batch_id: str
    chain_hash: str | None = None
    ipfs_cid: str | None = None
    events: list[TimelineEvent]
    lot: LotInfo | None = None


class LiveInventoryItem(BaseModel):
    sku: str
    name: str
    available: bool
    remaining_slots: int
    message: str = ""


class LiveInventoryResponse(BaseModel):
    room_id: str
    items: list[LiveInventoryItem]
    query: str = ""


class ErrorResponse(BaseModel):
    error: str
    code: str = "unknown"
