"""FastAPI 应用工厂与 uvicorn 启动入口。"""

from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

from fastapi import FastAPI

from herness.api.live import TaskLiveHub
from herness.api.rag_routes import router as rag_router
from herness.api.routes import router
from herness.api.security import RateLimiter
from herness.api.store import TaskStore, close_task_store, create_task_store
from herness.config import Settings, get_settings
from herness.middleware.factory import close_middleware, create_middleware
from herness.middleware.protocol import DataMiddleware
from herness.observability.logging import configure_logging
from herness.observability.metrics import get_metrics_registry
from herness.observability.usage_store import close_usage_store, create_usage_store
from herness.orchestrator.cancellation import TaskCancellationRegistry
from herness.orchestrator.scheduler import Orchestrator


@asynccontextmanager
async def _default_lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings: Settings = app.state.settings
    if not hasattr(app.state, "middleware") or app.state.middleware is None:
        app.state.middleware = await create_middleware(settings)
    if not hasattr(app.state, "orchestrator") or app.state.orchestrator is None:
        app.state.orchestrator = Orchestrator(
            middleware=app.state.middleware,
            settings=settings,
            cancellation_registry=getattr(app.state, "cancellation_registry", None),
        )
    elif getattr(app.state.orchestrator, "_cancellation_registry", None) is None and getattr(
        app.state, "cancellation_registry", None
    ) is not None:
        app.state.orchestrator._cancellation_registry = app.state.cancellation_registry
    if not hasattr(app.state, "store") or app.state.store is None:
        app.state.store = create_task_store(settings)
    if not hasattr(app.state, "usage_store") or app.state.usage_store is None:
        app.state.usage_store = await create_usage_store(settings)
    from herness.observability.usage_recorder import bind_usage_store

    bind_usage_store(
        app.state.usage_store,
        metrics_enabled=settings.metrics_enabled,
    )
    try:
        yield
    finally:
        await close_middleware(app.state.middleware)
        close_task_store(app.state.store)
        await close_usage_store(getattr(app.state, "usage_store", None))
        from herness.observability.usage_recorder import bind_usage_store

        bind_usage_store(None)


def create_app(
    *,
    settings: Settings | None = None,
    orchestrator: Orchestrator | None = None,
    store: TaskStore | None = None,
    middleware: DataMiddleware | None = None,
    live_hub: TaskLiveHub | None = None,
    cancellation_registry: TaskCancellationRegistry | None = None,
    usage_store: Any | None = None,
) -> FastAPI:
    """创建 FastAPI 应用；测试时可注入 mock orchestrator / store。"""
    resolved_settings = settings or get_settings()
    configure_logging(structured=resolved_settings.structured_logging)
    resolved_live_hub = live_hub or TaskLiveHub()
    resolved_cancellation = cancellation_registry or TaskCancellationRegistry()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.settings = resolved_settings
        app.state.middleware = middleware
        app.state.orchestrator = orchestrator
        app.state.store = store
        app.state.live_hub = resolved_live_hub
        app.state.cancellation_registry = resolved_cancellation
        app.state.usage_store = usage_store
        app.state.rate_limiter = RateLimiter(
            limit=resolved_settings.rate_limit_per_user,
            window_seconds=float(resolved_settings.rate_limit_window_seconds),
        )
        async with _default_lifespan(app):
            yield

    app = FastAPI(
        title="Herness Agent API",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.include_router(router)
    app.include_router(rag_router)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/metrics")
    async def metrics() -> dict:
        """进程内运行时指标快照。"""
        return get_metrics_registry().snapshot()

    return app


app = create_app()


def main() -> None:
    """CLI 入口：herness-api 或 python -m herness.api.app"""
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "herness.api.app:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=False,
    )


if __name__ == "__main__":
    main()
