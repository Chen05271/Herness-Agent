"""农业电商 BFF 集成测试 — mock 客户端、HTTP 客户端、工具策略。"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from herness.agents.tool_policy import globally_enabled_tools
from herness.config import Settings
from herness.integrations.agri_commerce.factory import build_agri_commerce_client
from herness.integrations.agri_commerce.http_client import HttpAgriCommerceClient
from herness.integrations.agri_commerce.mock_client import MockAgriCommerceClient
from herness.integrations.agri_commerce.mock_data import demo_user_id
from herness.integrations.agri_commerce import tools as agri_tools


@pytest.fixture
def demo_user() -> str:
    return demo_user_id()


@pytest.mark.asyncio
async def test_mock_get_order(demo_user: str) -> None:
    client = MockAgriCommerceClient()
    order = await client.get_order(demo_user, "ORD-20260705-001")
    assert order.status == "picking"
    assert order.trace_id == "TRACE-20260705-a3"
    assert order.sku_name == "蓝莓 80+"
    assert order.batch_id == "LOT-A3-0714"


@pytest.mark.asyncio
async def test_mock_get_order_wrong_user(demo_user: str) -> None:
    client = MockAgriCommerceClient()
    with pytest.raises(Exception, match="订单不存在"):
        await client.get_order("other-user", "ORD-20260705-001")


@pytest.mark.asyncio
async def test_mock_order_timeline(demo_user: str) -> None:
    client = MockAgriCommerceClient()
    timeline = await client.get_order_timeline(demo_user, "ORD-20260705-001")
    assert timeline.status == "picking"
    assert any(e.robot_id == "PICK-07" for e in timeline.events)


@pytest.mark.asyncio
async def test_mock_trace_batch() -> None:
    client = MockAgriCommerceClient()
    trace = await client.trace_batch("TRACE-20260705-a3")
    assert trace.lot is not None
    assert trace.lot.brix == 14.2
    assert trace.chain_hash.startswith("0x")


@pytest.mark.asyncio
async def test_mock_live_inventory() -> None:
    client = MockAgriCommerceClient()
    live = await client.get_live_inventory_hint("live-room-01", q="蓝莓")
    assert len(live.items) >= 1
    assert "蓝莓" in live.items[0].name


@pytest.mark.asyncio
async def test_tool_get_order_returns_json(demo_user: str) -> None:
    client = MockAgriCommerceClient()
    text = await agri_tools.tool_get_order(client, demo_user, "ORD-20260705-001")
    assert "ORD-20260705-001" in text
    assert "picking" in text


def test_build_client_mock_mode() -> None:
    settings = Settings(agri_commerce_enabled=True, agri_commerce_mode="mock")
    client = build_agri_commerce_client(settings)
    assert isinstance(client, MockAgriCommerceClient)


def test_build_client_http_mode() -> None:
    settings = Settings(
        agri_commerce_enabled=True,
        agri_commerce_mode="http",
        agri_commerce_base_url="http://localhost:9000/v1",
    )
    client = build_agri_commerce_client(settings)
    assert isinstance(client, HttpAgriCommerceClient)


def test_build_client_http_requires_base_url() -> None:
    settings = Settings(agri_commerce_enabled=True, agri_commerce_mode="http")
    with pytest.raises(ValueError, match="AGRI_COMMERCE_BASE_URL"):
        build_agri_commerce_client(settings)


def test_globally_enabled_tools_includes_agri() -> None:
    settings = Settings(agri_commerce_enabled=True)
    tools = globally_enabled_tools(settings)
    assert "get_order" in tools
    assert "trace_batch" in tools


@pytest.mark.asyncio
async def test_http_client_get_order() -> None:
    client = HttpAgriCommerceClient(
        base_url="http://bff.example/v1",
        api_key="secret",
    )
    payload = {
        "order_id": "ORD-1",
        "user_id": "u1",
        "status": "picking",
        "sku": "SKU-1",
        "sku_name": "测试",
        "trace_id": "T-1",
        "batch_id": None,
        "amount_cny": 1.0,
        "estimated_pick_start": None,
        "created_at": "2026-07-05T14:10:00+00:00",
    }
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json = MagicMock(return_value=payload)
    mock_http = AsyncMock()
    mock_http.request = AsyncMock(return_value=mock_response)
    mock_http.__aenter__ = AsyncMock(return_value=mock_http)
    mock_http.__aexit__ = AsyncMock(return_value=None)

    with patch("herness.integrations.agri_commerce.http_client.httpx.AsyncClient", return_value=mock_http):
        order = await client.get_order("u1", "ORD-1")

    assert order.order_id == "ORD-1"
    mock_http.request.assert_awaited_once()
    call_kwargs = mock_http.request.await_args.kwargs
    assert call_kwargs["headers"]["X-User-Id"] == "u1"
    assert call_kwargs["headers"]["Authorization"] == "Bearer secret"
