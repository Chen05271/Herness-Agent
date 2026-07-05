"""Redis 连接工厂 — 兼容 Redis 5.x（RESP2）。"""

from __future__ import annotations

from typing import Any

DEFAULT_REDIS_PROTOCOL = 2


def create_sync_redis(url: str, **kwargs: Any) -> Any:
    """创建同步 Redis 客户端（TaskStore 等同步场景）。"""
    try:
        import redis
    except ImportError as exc:
        raise ImportError(
            "Redis 功能需要 redis 包，请安装: pip install 'herness-agent[redis]'"
        ) from exc

    return redis.Redis.from_url(
        url,
        decode_responses=True,
        protocol=DEFAULT_REDIS_PROTOCOL,
        **kwargs,
    )


async def create_async_redis(url: str, **kwargs: Any) -> Any:
    """创建异步 Redis 客户端（中台缓存 / 队列）。"""
    try:
        import redis.asyncio as aioredis
    except ImportError as exc:
        raise ImportError(
            "Redis 功能需要 redis 包，请安装: pip install 'herness-agent[redis]'"
        ) from exc

    return aioredis.from_url(
        url,
        decode_responses=True,
        protocol=DEFAULT_REDIS_PROTOCOL,
        **kwargs,
    )


async def close_async_redis(client: Any) -> None:
    """关闭异步 Redis 连接。"""
    if client is not None:
        await client.aclose()
