"""中台工厂单元测试。"""

import pytest

fakeredis = pytest.importorskip("fakeredis")

from herness.config import Settings
from herness.middleware.factory import create_middleware
from herness.middleware.redis_augment import RedisAugmentedMiddleware
from herness.middleware.stub import InMemoryMiddleware


async def test_create_middleware_uses_memory_without_dsn() -> None:
    settings = Settings(postgres_dsn="", redis_url="")
    middleware = await create_middleware(settings)
    assert isinstance(middleware, InMemoryMiddleware)


async def test_create_middleware_wraps_redis(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = fakeredis.aioredis.FakeRedis(decode_responses=True)

    async def fake_create_async_redis(url: str):
        return fake

    monkeypatch.setattr(
        "herness.middleware.redis_augment.create_async_redis",
        fake_create_async_redis,
    )

    settings = Settings(postgres_dsn="", redis_url="redis://localhost:6379")
    middleware = await create_middleware(settings)
    assert isinstance(middleware, RedisAugmentedMiddleware)
    await middleware.close()
    await fake.aclose()
