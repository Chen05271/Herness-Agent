"""FastAPI 应用工厂与 uvicorn 启动入口。"""

from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI

from herness.api.routes import router
from herness.api.store import TaskStore, close_task_store, create_task_store
from herness.config import Settings, get_settings
from herness.middleware.factory import close_middleware, create_middleware
from herness.middleware.protocol import DataMiddleware
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
        )
    if not hasattr(app.state, "store") or app.state.store is None:
        app.state.store = create_task_store(settings)
    try:
        yield
    finally:
        await close_middleware(app.state.middleware)
        close_task_store(app.state.store)


def create_app(
    *,
    settings: Settings | None = None,
    orchestrator: Orchestrator | None = None,
    store: TaskStore | None = None,
    middleware: DataMiddleware | None = None,
) -> FastAPI:
    """创建 FastAPI 应用；测试时可注入 mock orchestrator / store。"""
    resolved_settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.settings = resolved_settings
        app.state.middleware = middleware
        app.state.orchestrator = orchestrator
        app.state.store = store
        async with _default_lifespan(app):
            yield

    app = FastAPI(
        title="Herness Agent API",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.include_router(router)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

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
