"""中台工厂 — 按配置选择 InMemory / Postgres，并按需挂载 Redis 增强层。"""

from typing import Any

from herness.config import Settings
from herness.middleware.redis_augment import RedisAugmentedMiddleware
from herness.middleware.stub import InMemoryMiddleware


async def create_middleware(settings: Settings) -> Any:
    """创建中台实例；Postgres + Redis 可组合使用。"""
    if settings.postgres_dsn:
        from herness.middleware.postgres import PostgresMiddleware

        inner: Any = PostgresMiddleware(settings.postgres_dsn)
        await inner.connect()
    else:
        inner = InMemoryMiddleware()

    if settings.redis_url:
        middleware = RedisAugmentedMiddleware(
            inner,
            settings.redis_url,
            memory_ttl_seconds=settings.redis_memory_ttl_seconds,
        )
        await middleware.connect()
        return middleware

    return inner


async def close_middleware(middleware: Any) -> None:
    """释放中台资源（Postgres 连接池 / Redis 连接等）。"""
    close = getattr(middleware, "close", None)
    if close is not None:
        await close()
