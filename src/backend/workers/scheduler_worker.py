"""Dedicated scheduler process entrypoint."""

from __future__ import annotations

import asyncio
import logging
import signal

from backend.db.session import async_session_maker
from backend.services.sync_scheduler import DailySyncScheduler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


async def _run() -> None:
    scheduler = DailySyncScheduler(async_session_maker)

    def _handle_signal(*_) -> None:
        logger.info("Received shutdown signal. Stopping scheduler worker...")
        scheduler.stop()

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)
    await scheduler.start()


if __name__ == "__main__":
    asyncio.run(_run())
