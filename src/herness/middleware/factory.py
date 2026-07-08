"""中台工厂 — 按配置选择 InMemory / Postgres，并按需挂载 Redis 增强层。"""

from typing import Any

from herness.config import Settings
from herness.middleware.embeddings import build_embedding_client
from herness.middleware.redis_augment import RedisAugmentedMiddleware
from herness.middleware.stub import InMemoryMiddleware


def _build_embedding_client(settings: Settings) -> Any:
    if settings.hereness_vector_enabled or settings.rag_vector_enabled:
        return build_embedding_client(settings)
    return None


async def create_middleware(settings: Settings) -> Any:
    """创建中台实例；Postgres + Redis 可组合使用。"""
    embedding_client = _build_embedding_client(settings)

    if settings.postgres_dsn:
        from herness.middleware.postgres import PostgresMiddleware

        inner: Any = PostgresMiddleware(
            settings.postgres_dsn,
            settings=settings,
            hereness_enabled=settings.hereness_enabled,
            hereness_vector_enabled=settings.hereness_vector_enabled,
            embedding_client=embedding_client,
            embedding_dimensions=settings.embedding_dimensions,
            hereness_vector_top_k=settings.hereness_vector_top_k,
            hereness_vector_min_similarity=settings.hereness_vector_min_similarity,
            hereness_conflict_decay_factor=settings.hereness_conflict_decay_factor,
            hereness_superseded_threshold=settings.hereness_superseded_threshold,
        )
        await inner.connect()
    else:
        inner = InMemoryMiddleware(
            hereness_enabled=settings.hereness_enabled,
            rag_enabled=settings.rag_enabled,
        )
        inner.configure_hereness_conflict(
            decay_factor=settings.hereness_conflict_decay_factor,
            superseded_threshold=settings.hereness_superseded_threshold,
        )
        if settings.rag_enabled:
            inner.configure_rag(settings, embedding_client=embedding_client)

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
