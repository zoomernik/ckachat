from __future__ import annotations

import asyncio
import logging
import tempfile
from pathlib import Path
from typing import Any

import yt_dlp

from .config import Settings
from .models import DownloadResult, MediaMeta, QualityOption
from .solver import resolve_youtube_solver

logger = logging.getLogger(__name__)


class YtDlpClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def fetch_info(self, url: str) -> dict[str, Any]:
        solver_payload = await resolve_youtube_solver(
            mode=self.settings.youtube_solver_mode,
            deno_bin=self.settings.deno_bin,
            deno_solver_script=self.settings.deno_solver_script,
            url=url,
        )

        def _run() -> dict[str, Any]:
            opts: dict[str, Any] = {
                "skip_download": True,
                "noplaylist": True,
                "quiet": True,
                "no_warnings": True,
                "socket_timeout": self.settings.ytdlp_socket_timeout,
                "retries": self.settings.ytdlp_retries,
                "nocheckcertificate": True,
            }
            cookie_file = solver_payload.cookie_file or self.settings.cookie_file
            if cookie_file:
                opts["cookiefile"] = cookie_file
            if solver_payload.extractor_args:
                opts["extractor_args"] = solver_payload.extractor_args

            with yt_dlp.YoutubeDL(opts) as ydl:
                return ydl.extract_info(url, download=False)

        return await asyncio.to_thread(_run)

    def build_quality_candidates(self, info: dict[str, Any]) -> list[QualityOption]:
        formats = info.get("formats") or []
        candidates: dict[int, QualityOption] = {}

        for fmt in formats:
            height = fmt.get("height")
            if not isinstance(height, int):
                continue
            if fmt.get("vcodec") in (None, "none") or fmt.get("acodec") in (None, "none"):
                continue

            ext = str(fmt.get("ext") or "").lower()
            if ext not in {"mp4", "webm"}:
                continue

            filesize = fmt.get("filesize") or fmt.get("filesize_approx")
            if isinstance(filesize, (int, float)) and filesize > self.settings.max_upload_mb * 1024 * 1024:
                continue

            option = QualityOption(
                format_id=str(fmt.get("format_id")),
                height=height,
                ext=ext,
                filesize=int(filesize) if isinstance(filesize, (int, float)) else None,
                tbr=fmt.get("tbr"),
            )
            previous = candidates.get(height)
            if previous is None or (option.tbr or 0) > (previous.tbr or 0):
                candidates[height] = option

        return sorted(candidates.values(), key=lambda item: item.height)[: self.settings.max_quality_buttons]

    def extract_media_meta(self, info: dict[str, Any], source_url: str) -> MediaMeta:
        title = str(info.get("title") or "Без названия")
        duration = info.get("duration")
        duration_int = int(duration) if isinstance(duration, (int, float)) else None
        return MediaMeta(title=title, duration=duration_int, source_url=source_url)

    async def download(
        self,
        url: str,
        platform: str,
        format_id: str | None,
    ) -> tuple[DownloadResult, tempfile.TemporaryDirectory[str]]:
        temp_dir = tempfile.TemporaryDirectory(prefix="video_", dir=self.settings.temp_root)
        output_template = str(Path(temp_dir.name) / "media.%(ext)s")

        if format_id:
            format_expr = (
                f"{format_id}[vcodec!=none][acodec!=none]/"
                f"best[vcodec!=none][acodec!=none][filesize<{self.settings.max_upload_mb}M]/"
                f"best[vcodec!=none][acodec!=none]/best"
            )
        else:
            format_expr = (
                f"best[ext=mp4][vcodec!=none][acodec!=none][filesize<{self.settings.max_upload_mb}M]/"
                f"best[vcodec!=none][acodec!=none][filesize<{self.settings.max_upload_mb}M]/"
                f"best[ext=mp4][vcodec!=none][acodec!=none]/"
                f"best[vcodec!=none][acodec!=none]/best"
            )

        solver_payload = await resolve_youtube_solver(
            mode=self.settings.youtube_solver_mode,
            deno_bin=self.settings.deno_bin,
            deno_solver_script=self.settings.deno_solver_script,
            url=url,
        )

        def _run() -> DownloadResult:
            opts: dict[str, Any] = {
                "format": format_expr,
                "outtmpl": output_template,
                "noplaylist": True,
                "quiet": True,
                "no_warnings": True,
                "socket_timeout": self.settings.ytdlp_socket_timeout,
                "retries": self.settings.ytdlp_retries,
                "nocheckcertificate": True,
            }
            cookie_file = solver_payload.cookie_file or self.settings.cookie_file
            if cookie_file:
                opts["cookiefile"] = cookie_file
            if solver_payload.extractor_args:
                opts["extractor_args"] = solver_payload.extractor_args

            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=True)
                file_path = ydl.prepare_filename(info)
                path = Path(file_path)
                if not path.exists():
                    for candidate in Path(temp_dir.name).glob("media.*"):
                        if candidate.exists():
                            path = candidate
                            break

                duration = info.get("duration")
                duration_int = int(duration) if isinstance(duration, (int, float)) else None
                return DownloadResult(
                    file_path=str(path),
                    title=str(info.get("title") or "Без названия"),
                    ext=path.suffix.lower().lstrip("."),
                    duration=duration_int,
                    platform=platform,
                )

        try:
            result = await asyncio.to_thread(_run)
            return result, temp_dir
        except Exception:
            temp_dir.cleanup()
            raise
