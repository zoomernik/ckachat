from __future__ import annotations

import asyncio
import logging
import sys
from contextlib import suppress
from pathlib import Path

from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application

# If host runs this file directly (python /app/video_bot/app.py),
# make sure parent folder (/app) is in sys.path so `video_bot` package is importable.
if __package__ in (None, ""):
    parent = Path(__file__).resolve().parent.parent
    parent_str = str(parent)
    if parent_str not in sys.path:
        sys.path.insert(0, parent_str)

try:
    from .config import load_settings
    from .download_queue import DownloadQueue
    from .logging_setup import setup_logging
    from .telegram_handlers import BotHandlers
    from .yt_client import YtDlpClient
except ImportError:
    # Compatibility mode for hosts that run `python video_bot/app.py` directly.
    from video_bot.config import load_settings
    from video_bot.download_queue import DownloadQueue
    from video_bot.logging_setup import setup_logging
    from video_bot.telegram_handlers import BotHandlers
    from video_bot.yt_client import YtDlpClient

logger = logging.getLogger(__name__)


async def _start_healthcheck_server(host: str, port: int) -> asyncio.AbstractServer:
    async def _handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            request = await reader.read(1024)
            if b"GET /health" in request:
                body = b"ok"
                response = (
                    b"HTTP/1.1 200 OK\r\n"
                    b"Content-Type: text/plain\r\n"
                    + f"Content-Length: {len(body)}\r\n".encode("ascii")
                    + b"Connection: close\r\n\r\n"
                    + body
                )
            else:
                body = b"not found"
                response = (
                    b"HTTP/1.1 404 Not Found\r\n"
                    b"Content-Type: text/plain\r\n"
                    + f"Content-Length: {len(body)}\r\n".encode("ascii")
                    + b"Connection: close\r\n\r\n"
                    + body
                )
            writer.write(response)
            await writer.drain()
        finally:
            writer.close()
            with suppress(Exception):
                await writer.wait_closed()

    server = await asyncio.start_server(_handle, host=host, port=port)
    logger.info("Healthcheck server started on %s:%s", host, port)
    return server


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
    health_server: asyncio.AbstractServer | None = None

    logger.info("Bot starting")
    await app.initialize()
    await app.start()
    await app.updater.start_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)
    if settings.healthcheck_enabled:
        health_server = await _start_healthcheck_server(
            host=settings.healthcheck_host, port=settings.healthcheck_port
        )

    try:
        while True:
            await asyncio.sleep(3600)
    finally:
        logger.info("Bot stopping")
        if health_server:
            health_server.close()
            await health_server.wait_closed()
        await app.updater.stop()
        await app.stop()
        await app.shutdown()
        await queue.stop()


def main() -> None:
    asyncio.run(run())
