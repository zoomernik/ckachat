from __future__ import annotations

import asyncio
import logging

from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application

from .config import load_settings
from .download_queue import DownloadQueue
from .logging_setup import setup_logging
from .telegram_handlers import BotHandlers
from .yt_client import YtDlpClient

logger = logging.getLogger(__name__)


async def run() -> None:
    load_dotenv()
    setup_logging()
    settings = load_settings()

    yt_client = YtDlpClient(settings)
    queue = DownloadQueue(settings=settings, client=yt_client)
    await queue.start()

    app = Application.builder().token(settings.telegram_bot_token).build()
    handlers = BotHandlers(settings=settings, yt_client=yt_client, queue=queue)
    handlers.register(app)

    logger.info("Bot starting")
    await app.initialize()
    await app.start()
    await app.updater.start_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)

    try:
        while True:
            await asyncio.sleep(3600)
    finally:
        logger.info("Bot stopping")
        await app.updater.stop()
        await app.stop()
        await app.shutdown()
        await queue.stop()


def main() -> None:
    asyncio.run(run())
