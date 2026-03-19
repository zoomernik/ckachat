import asyncio
import logging
import os
import re
import tempfile
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv
from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters
import yt_dlp

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("video_bot")

URL_RE = re.compile(r"https?://[^\s]+", re.IGNORECASE)
SUPPORTED_PLATFORMS = {
    "youtube.com": "YouTube",
    "youtu.be": "YouTube",
    "vk.com": "VK",
    "m.vk.com": "VK",
    "instagram.com": "Instagram",
    "www.instagram.com": "Instagram",
}
MAX_UPLOAD_MB = 48


def normalize_domain(url: str) -> str:
    host = urlparse(url).netloc.lower().strip()
    if host.startswith("www."):
        host = host[4:]
    return host


def detect_platform(url: str) -> str | None:
    host = normalize_domain(url)
    for domain, platform in SUPPORTED_PLATFORMS.items():
        if host == domain or host.endswith("." + domain):
            return platform
    return None


def get_first_url(text: str | None) -> str | None:
    if not text:
        return None
    match = URL_RE.search(text)
    return match.group(0) if match else None


def download_video(url: str, temp_dir: str) -> tuple[str, str | None]:
    output_template = str(Path(temp_dir) / "video.%(ext)s")
    ydl_opts = {
        "format": f"bv*[ext=mp4][filesize<{MAX_UPLOAD_MB}M]+ba[ext=m4a]/b[ext=mp4][filesize<{MAX_UPLOAD_MB}M]/b[filesize<{MAX_UPLOAD_MB}M]/best",
        "merge_output_format": "mp4",
        "outtmpl": output_template,
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "socket_timeout": 20,
        "retries": 3,
        "nocheckcertificate": True,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        video_path = ydl.prepare_filename(info)

        # If merged output was created, yt-dlp may return pre-merge extension.
        if not Path(video_path).exists():
            mp4_candidate = str(Path(video_path).with_suffix(".mp4"))
            if Path(mp4_candidate).exists():
                video_path = mp4_candidate

        title = info.get("title")
        return video_path, title


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Привет. Отправь ссылку на видео (YouTube, VK, Instagram), и я попробую прислать его прямо в чат."
    )


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Поддерживаемые ссылки: YouTube, VK, Instagram.\n"
        "Просто отправь ссылку сообщением."
    )


async def handle_link(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.message
    if not message:
        return

    url = get_first_url(message.text)
    if not url:
        await message.reply_text("Не вижу ссылку. Отправь корректный URL.")
        return

    platform = detect_platform(url)
    if not platform:
        await message.reply_text(
            "Пока поддерживаются только YouTube, VK и Instagram ссылки."
        )
        return

    await message.reply_text(f"Ссылка распознана: {platform}. Начинаю обработку...")
    await context.bot.send_chat_action(chat_id=message.chat_id, action=ChatAction.UPLOAD_VIDEO)

    try:
        with tempfile.TemporaryDirectory() as temp_dir:
            video_path, title = await asyncio.to_thread(download_video, url, temp_dir)

            file_size_mb = Path(video_path).stat().st_size / (1024 * 1024)
            if file_size_mb > MAX_UPLOAD_MB:
                await message.reply_text(
                    f"Видео получилось слишком большим ({file_size_mb:.1f} MB). "
                    f"Лимит отправки ботом сейчас настроен на {MAX_UPLOAD_MB} MB."
                )
                return

            caption = f"{platform}"
            if title:
                caption = f"{platform}\n{title}"

            with open(video_path, "rb") as video_file:
                await message.reply_video(
                    video=video_file,
                    caption=caption[:1024],
                    supports_streaming=True,
                )
    except Exception as exc:
        logger.exception("Failed to process URL: %s", url)
        await message.reply_text(
            "Не удалось скачать или отправить видео. "
            "Проверь ссылку и попробуй еще раз."
        )


async def unknown(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message:
        await update.message.reply_text("Отправь ссылку на видео одним сообщением.")


def main() -> None:
    load_dotenv()
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise RuntimeError("Не найден TELEGRAM_BOT_TOKEN в .env")

    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_link))
    app.add_handler(MessageHandler(filters.ALL, unknown))

    logger.info("Bot started")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
