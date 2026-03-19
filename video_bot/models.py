from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class QualityOption:
    format_id: str
    height: int
    ext: str
    filesize: int | None
    tbr: float | int | None


@dataclass(frozen=True)
class MediaMeta:
    title: str
    duration: int | None
    source_url: str


@dataclass(frozen=True)
class DownloadResult:
    file_path: str
    title: str
    ext: str
    duration: int | None
    platform: str
