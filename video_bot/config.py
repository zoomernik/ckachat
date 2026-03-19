from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    telegram_bot_token: str
    max_upload_mb: int = 48
    max_duration_seconds: int = 60 * 30
    max_parallel_downloads: int = 2
    per_user_single_active: bool = True
    max_quality_buttons: int = 8
    temp_root: str = "/tmp/video_bot"
    ytdlp_socket_timeout: int = 20
    ytdlp_retries: int = 3
    cookie_file: str | None = None
    youtube_solver_mode: str = "off"  # off | deno_ejs
    deno_bin: str = "deno"
    deno_solver_script: str | None = None
    max_download_attempts: int = 2
    retry_backoff_seconds: int = 2
    job_timeout_seconds: int = 900
    healthcheck_enabled: bool = True
    healthcheck_host: str = "0.0.0.0"
    healthcheck_port: int = 8080


def _int_env(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    return int(raw)


def load_settings() -> Settings:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        raise RuntimeError("Не найден TELEGRAM_BOT_TOKEN в переменных окружения.")

    temp_root = os.getenv("TEMP_ROOT", "/tmp/video_bot").strip() or "/tmp/video_bot"
    Path(temp_root).mkdir(parents=True, exist_ok=True)

    return Settings(
        telegram_bot_token=token,
        max_upload_mb=_int_env("MAX_UPLOAD_MB", 48),
        max_duration_seconds=_int_env("MAX_DURATION_SECONDS", 1800),
        max_parallel_downloads=max(1, _int_env("MAX_PARALLEL_DOWNLOADS", 2)),
        per_user_single_active=os.getenv("PER_USER_SINGLE_ACTIVE", "1") == "1",
        max_quality_buttons=max(1, _int_env("MAX_QUALITY_BUTTONS", 8)),
        temp_root=temp_root,
        ytdlp_socket_timeout=_int_env("YTDLP_SOCKET_TIMEOUT", 20),
        ytdlp_retries=_int_env("YTDLP_RETRIES", 3),
        cookie_file=os.getenv("YTDLP_COOKIE_FILE") or None,
        youtube_solver_mode=(os.getenv("YOUTUBE_SOLVER_MODE", "off") or "off").strip().lower(),
        deno_bin=os.getenv("DENO_BIN", "deno").strip() or "deno",
        deno_solver_script=os.getenv("DENO_SOLVER_SCRIPT") or None,
        max_download_attempts=max(1, _int_env("MAX_DOWNLOAD_ATTEMPTS", 2)),
        retry_backoff_seconds=max(0, _int_env("RETRY_BACKOFF_SECONDS", 2)),
        job_timeout_seconds=max(30, _int_env("JOB_TIMEOUT_SECONDS", 900)),
        healthcheck_enabled=os.getenv("HEALTHCHECK_ENABLED", "1") == "1",
        healthcheck_host=os.getenv("HEALTHCHECK_HOST", "0.0.0.0").strip() or "0.0.0.0",
        healthcheck_port=max(1, _int_env("HEALTHCHECK_PORT", 8080)),
    )
