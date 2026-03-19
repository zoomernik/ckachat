from __future__ import annotations

import asyncio
import logging
import re
import secrets
from tempfile import TemporaryDirectory

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ChatAction
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from .config import Settings
from .download_queue import DownloadQueue
from .models import DownloadResult, MediaMeta, QualityOption
from .platforms import detect_platform
from .yt_client import YtDlpClient

logger = logging.getLogger(__name__)
URL_RE = re.compile(r"https?://[^\s]+", re.IGNORECASE)


def get_first_url(text: str | None) -> str | None:
    if not text:
        return None
    match = URL_RE.search(text)
    return match.group(0) if match else None


def _build_quality_keyboard(token: str, options: list[QualityOption]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []

    for index, opt in enumerate(options, start=1):
        size_label = ""
        if opt.filesize:
            size_mb = opt.filesize / (1024 * 1024)
            size_label = f" {size_mb:.1f}MB"
        text = f"{opt.height}p {opt.ext}{size_label}"
        row.append(InlineKeyboardButton(text=text, callback_data=f"dl:{token}:{opt.format_id}"))
        if index % 2 == 0:
            rows.append(row)
            row = []

    if row:
        rows.append(row)

    rows.append([InlineKeyboardButton(text="Auto", callback_data=f"dl:{token}:auto")])
    return InlineKeyboardMarkup(rows)


class BotHandlers:
    def __init__(self, settings: Settings, yt_client: YtDlpClient, queue: DownloadQueue) -> None:
        self.settings = settings
        self.yt_client = yt_client
        self.queue = queue

    def register(self, app: Application) -> None:
        app.add_handler(CommandHandler("start", self.start))
        app.add_handler(CommandHandler("help", self.help_cmd))
        app.add_handler(CallbackQueryHandler(self.handle_quality_pick, pattern=r"^dl:"))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_link))
        app.add_handler(MessageHandler(filters.ALL, self.unknown))
        app.add_error_handler(self.on_error)

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.message:
            await update.message.reply_text(
                "Привет. Отправь ссылку на видео (YouTube/VK/Instagram/RuTube).\n"
                "Я покажу качества и отправлю файл прямо в чат."
            )

    async def help_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.message:
            await update.message.reply_text(
                "Как пользоваться:\n"
                "1) Отправь ссылку\n"
                "2) Выбери качество\n"
                "3) Дождись отправки\n\n"
                f"Лимиты: до {self.settings.max_upload_mb} MB и до {self.settings.max_duration_seconds // 60} минут."
            )

    async def handle_link(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        message = update.message
        if not message:
            return

        url = get_first_url(message.text)
        if not url:
            await message.reply_text("Не вижу ссылку. Отправь корректный URL.")
            return

        platform = detect_platform(url)
        if not platform:
            await message.reply_text("Поддерживаются ссылки: YouTube, VK, Instagram, RuTube.")
            return

        await message.reply_text(f"Ссылка распознана: {platform}. Получаю метаданные...")

        try:
            info = await self.yt_client.fetch_info(url)
            meta = self.yt_client.extract_media_meta(info, source_url=url)
            if meta.duration and meta.duration > self.settings.max_duration_seconds:
                await message.reply_text(
                    f"Видео слишком длинное: {meta.duration // 60} мин. Лимит: {self.settings.max_duration_seconds // 60} мин."
                )
                return

            options = self.yt_client.build_quality_candidates(info)
            token = secrets.token_hex(8)
            context.user_data.setdefault("pending", {})[token] = {
                "url": url,
                "platform": platform,
                "title": meta.title,
            }

            if not options:
                keyboard = InlineKeyboardMarkup(
                    [[InlineKeyboardButton("Auto", callback_data=f"dl:{token}:auto")]]
                )
                await message.reply_text(
                    f"{platform}\n{meta.title}\n\nКачества не найдены, можно попробовать авто-режим.",
                    reply_markup=keyboard,
                )
                return

            keyboard = _build_quality_keyboard(token, options)
            await message.reply_text(f"{platform}\n{meta.title}\n\nВыбери качество:", reply_markup=keyboard)

        except Exception:
            logger.exception("Metadata extraction failed: %s", url)
            await message.reply_text("Не удалось получить метаданные. Попробуй другую ссылку.")

    async def handle_quality_pick(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        if not query or not query.data or not query.message:
            return

        await query.answer()
        parts = query.data.split(":", 2)
        if len(parts) != 3:
            return

        token = parts[1]
        selected = parts[2]
        pending = context.user_data.get("pending", {})
        payload = pending.pop(token, None)
        if not payload:
            await query.edit_message_text("Запрос устарел. Отправь ссылку заново.")
            return

        user_id = query.from_user.id
        url = str(payload["url"])
        platform = str(payload["platform"])
        format_id = None if selected == "auto" else selected

        try:
            future = await self.queue.enqueue(user_id=user_id, url=url, platform=platform, format_id=format_id)
        except RuntimeError:
            await query.edit_message_text(
                "У тебя уже есть активная загрузка. Дождись завершения и отправь ссылку снова."
            )
            return

        await query.edit_message_text(
            f"Добавил в очередь. Позиция: {self.queue.queued_count()}. Скачиваю..."
        )
        await context.bot.send_chat_action(chat_id=query.message.chat_id, action=ChatAction.UPLOAD_VIDEO)

        temp_dir: TemporaryDirectory[str] | None = None
        try:
            result, temp_dir = await future
            await self._send_media(query, result)
        except Exception:
            logger.exception("Download/send failed for URL: %s", url)
            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text="Не удалось скачать или отправить видео. Попробуй другое качество или ссылку.",
            )
        finally:
            if temp_dir:
                temp_dir.cleanup()

    async def _send_media(self, query, result: DownloadResult) -> None:
        if not query.message:
            return

        file_size_mb = 0.0
        try:
            from pathlib import Path

            path = Path(result.file_path)
            file_size_mb = path.stat().st_size / (1024 * 1024)
        except Exception:
            pass

        if file_size_mb > self.settings.max_upload_mb:
            await query.message.reply_text(
                f"Файл слишком большой ({file_size_mb:.1f} MB). Лимит: {self.settings.max_upload_mb} MB."
            )
            return

        if result.duration and result.duration > self.settings.max_duration_seconds:
            await query.message.reply_text(
                f"Видео слишком длинное ({result.duration // 60} мин). Лимит: {self.settings.max_duration_seconds // 60} мин."
            )
            return

        caption = f"{result.platform}\n{result.title}"[:1024]
        with open(result.file_path, "rb") as media_file:
            if result.ext == "mp4":
                await query.message.reply_video(
                    video=media_file,
                    caption=caption,
                    supports_streaming=True,
                )
            else:
                await query.message.reply_document(document=media_file, caption=caption)

    async def unknown(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.message:
            await update.message.reply_text("Отправь ссылку на видео одним сообщением.")

    async def on_error(self, update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
        logger.exception("Unhandled bot error. Update=%s", update, exc_info=context.error)
