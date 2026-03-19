import asyncio
import logging
import os
import re
import secrets
import tempfile
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv
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
MAX_FORMAT_BUTTONS = 6


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


def fetch_video_info(url: str) -> dict:
    ydl_opts = {
        "skip_download": True,
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "socket_timeout": 20,
        "retries": 3,
        "nocheckcertificate": True,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        return ydl.extract_info(url, download=False)


def build_quality_candidates(info: dict) -> list[dict]:
    formats = info.get("formats") or []
    candidates: dict[int, dict] = {}

    for fmt in formats:
        height = fmt.get("height")
        if not height:
            continue

        # Telegram playback is most stable for ready-to-play streams.
        if fmt.get("vcodec") in (None, "none") or fmt.get("acodec") in (None, "none"):
            continue

        ext = (fmt.get("ext") or "").lower()
        if ext not in {"mp4", "webm"}:
            continue

        filesize = fmt.get("filesize") or fmt.get("filesize_approx")
        if filesize and filesize > MAX_UPLOAD_MB * 1024 * 1024:
            continue

        tbr = fmt.get("tbr") or 0
        prev = candidates.get(height)
        if not prev or tbr > (prev.get("tbr") or 0):
            candidates[height] = {
                "format_id": str(fmt.get("format_id")),
                "height": int(height),
                "ext": ext,
                "filesize": filesize,
                "tbr": tbr,
            }

    result = sorted(candidates.values(), key=lambda x: x["height"])[:MAX_FORMAT_BUTTONS]
    return result


def download_video(url: str, temp_dir: str, format_id: str | None = None) -> tuple[str, str | None]:
    output_template = str(Path(temp_dir) / "video.%(ext)s")
    if format_id:
        # Download only progressive format (video+audio in one stream) to avoid ffmpeg merge.
        format_expr = (
            f"{format_id}[vcodec!=none][acodec!=none]/"
            f"best[vcodec!=none][acodec!=none][filesize<{MAX_UPLOAD_MB}M]/"
            f"best[vcodec!=none][acodec!=none]/best"
        )
    else:
        format_expr = (
            f"best[ext=mp4][vcodec!=none][acodec!=none][filesize<{MAX_UPLOAD_MB}M]/"
            f"best[vcodec!=none][acodec!=none][filesize<{MAX_UPLOAD_MB}M]/"
            f"best[ext=mp4][vcodec!=none][acodec!=none]/"
            f"best[vcodec!=none][acodec!=none]/best"
        )

    ydl_opts = {
        "format": format_expr,
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

        if not Path(video_path).exists():
            mp4_candidate = str(Path(video_path).with_suffix(".mp4"))
            if Path(mp4_candidate).exists():
                video_path = mp4_candidate

        title = info.get("title")
        return video_path, title


def save_pending_request(context: ContextTypes.DEFAULT_TYPE, payload: dict) -> str:
    token = secrets.token_hex(6)
    pending = context.user_data.setdefault("pending", {})
    pending[token] = payload
    return token


def get_pending_request(context: ContextTypes.DEFAULT_TYPE, token: str) -> dict | None:
    pending = context.user_data.get("pending", {})
    return pending.pop(token, None)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Привет. Отправь ссылку на видео (YouTube, VK, Instagram), "
        "я покажу доступные качества и отправлю файл прямо в чат."
    )


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Поддерживаемые ссылки: YouTube, VK, Instagram.\n"
        "Отправь ссылку сообщением, затем выбери качество."
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
        await message.reply_text("Пока поддерживаются только YouTube, VK и Instagram ссылки.")
        return

    await message.reply_text(f"Ссылка распознана: {platform}. Получаю варианты качества...")

    try:
        info = await asyncio.to_thread(fetch_video_info, url)
        title = info.get("title") or "Без названия"
        options = build_quality_candidates(info)

        if not options:
            token = save_pending_request(
                context,
                {"url": url, "platform": platform, "title": title, "format_id": None},
            )
            keyboard = InlineKeyboardMarkup(
                [[InlineKeyboardButton("Auto", callback_data=f"dl:{token}:auto")]]
            )
            await message.reply_text(
                "Не удалось безопасно собрать список качеств, можно попробовать автозагрузку.",
                reply_markup=keyboard,
            )
            return

        token = save_pending_request(
            context,
            {"url": url, "platform": platform, "title": title, "options": options},
        )

        rows = []
        for opt in options:
            size_label = ""
            if opt.get("filesize"):
                size_mb = opt["filesize"] / (1024 * 1024)
                size_label = f" | {size_mb:.1f} MB"
            label = f"{opt['height']}p ({opt['ext']}){size_label}"
            rows.append(
                [
                    InlineKeyboardButton(
                        label,
                        callback_data=f"dl:{token}:{opt['format_id']}",
                    )
                ]
            )

        rows.append([InlineKeyboardButton("Auto", callback_data=f"dl:{token}:auto")])
        keyboard = InlineKeyboardMarkup(rows)
        await message.reply_text(f"{platform}\n{title}\n\nВыбери качество:", reply_markup=keyboard)

    except Exception:
        logger.exception("Failed to fetch formats for URL: %s", url)
        await message.reply_text(
            "Не удалось получить форматы видео. Проверь ссылку и попробуй еще раз."
        )


async def handle_quality_pick(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query or not query.data:
        return

    await query.answer()

    parts = query.data.split(":", 2)
    if len(parts) != 3 or parts[0] != "dl":
        return

    token = parts[1]
    selected = parts[2]
    payload = get_pending_request(context, token)
    if not payload:
        await query.edit_message_text("Запрос устарел. Отправь ссылку заново.")
        return

    url = payload["url"]
    platform = payload["platform"]
    title = payload.get("title")
    format_id = None if selected == "auto" else selected

    await query.edit_message_text("Скачиваю и отправляю видео...")
    await context.bot.send_chat_action(chat_id=query.message.chat_id, action=ChatAction.UPLOAD_VIDEO)

    try:
        with tempfile.TemporaryDirectory() as temp_dir:
            video_path, final_title = await asyncio.to_thread(download_video, url, temp_dir, format_id)

            file_size_mb = Path(video_path).stat().st_size / (1024 * 1024)
            if file_size_mb > MAX_UPLOAD_MB:
                await context.bot.send_message(
                    chat_id=query.message.chat_id,
                    text=(
                        f"Видео получилось слишком большим ({file_size_mb:.1f} MB). "
                        f"Лимит отправки сейчас {MAX_UPLOAD_MB} MB."
                    ),
                )
                return

            caption_title = final_title or title
            caption = platform if not caption_title else f"{platform}\n{caption_title}"

            with open(video_path, "rb") as video_file:
                await context.bot.send_video(
                    chat_id=query.message.chat_id,
                    video=video_file,
                    caption=caption[:1024],
                    supports_streaming=True,
                )
    except Exception:
        logger.exception("Failed to download/send URL: %s", url)
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text="Не удалось скачать или отправить видео. Попробуй другое качество или другую ссылку.",
        )


async def unknown(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message:
        await update.message.reply_text("Отправь ссылку на видео одним сообщением.")


async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.exception("Unhandled error while processing update: %s", update, exc_info=context.error)


def main() -> None:
    load_dotenv()
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise RuntimeError("Не найден TELEGRAM_BOT_TOKEN в .env")

    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CallbackQueryHandler(handle_quality_pick, pattern=r"^dl:"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_link))
    app.add_handler(MessageHandler(filters.ALL, unknown))
    app.add_error_handler(on_error)

    logger.info("Bot started")
    app.run_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True,
    )


if __name__ == "__main__":
    main()
