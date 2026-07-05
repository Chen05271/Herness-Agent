"""Dreaming Worker 独立进程入口。"""

from __future__ import annotations

import asyncio
import logging
import sys

from herness.config import get_settings
from herness.dreaming.synthesizer import MemorySynthesizer
from herness.dreaming.worker import DreamingWorker
from herness.middleware.factory import close_middleware, create_middleware
from herness.observability.logging import configure_logging

configure_logging(structured=get_settings().structured_logging)
logger = logging.getLogger(__name__)


async def run_dreaming_worker() -> None:
    settings = get_settings()
    if not settings.dreaming_enabled:
        logger.warning("DREAMING_ENABLED=false，仍启动 Worker（可设 DREAMING_ENABLED=true 显式启用）")

    middleware = await create_middleware(settings)
    synthesizer = MemorySynthesizer.from_settings(settings)
    worker = DreamingWorker(middleware, synthesizer, settings)

    try:
        await worker.run_forever()
    finally:
        await close_middleware(middleware)


def main() -> None:
    """CLI 入口：python -m herness.dreaming.app"""
    try:
        asyncio.run(run_dreaming_worker())
    except KeyboardInterrupt:
        logger.info("Dreaming Worker 已停止")
        sys.exit(0)


if __name__ == "__main__":
    main()
