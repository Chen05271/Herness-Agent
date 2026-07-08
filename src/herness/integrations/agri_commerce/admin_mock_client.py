"""运营后台 Mock 客户端。"""

from __future__ import annotations

from typing import Any


class MockAgriAdminClient:
    async def get_dashboard(self) -> dict[str, Any]:
        return {
            "totalOrders": 128,
            "pendingPaymentOrders": 3,
            "pendingPickOrders": 12,
            "totalProducts": 9,
            "onSaleProducts": 8,
        }

    async def list_orders(
        self,
        *,
        status: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> dict[str, Any]:
        orders = [
            {
                "orderId": "ORD-260707-004",
                "skuName": "阳光玫瑰 青提",
                "status": "pending_pick",
                "amountCny": 98.0,
            },
            {
                "orderId": "ORD-260707-007",
                "skuName": "树莓 特级",
                "status": "picking",
                "amountCny": 78.0,
            },
        ]
        if status:
            orders = [o for o in orders if o["status"] == status]
        return {"orders": orders[:limit], "total": len(orders)}

    async def get_order(self, order_id: str) -> dict[str, Any]:
        return {
            "orderId": order_id,
            "skuName": "蓝莓 80+",
            "status": "pending_pick",
            "amountCny": 128.0,
        }

    async def list_products(self, *, limit: int = 20, offset: int = 0) -> dict[str, Any]:
        products = [
            {"sku": "SKU-BB-80", "name": "蓝莓 80+", "status": "on_sale", "priceCny": 128.0},
            {"sku": "SKU-CH-1", "name": "樱桃 一级果", "status": "on_sale", "priceCny": 89.0},
        ]
        return {"products": products[:limit], "total": len(products)}
