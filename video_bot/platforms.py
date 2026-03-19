from __future__ import annotations

from urllib.parse import urlparse

SUPPORTED_PLATFORMS = {
    "youtube.com": "YouTube",
    "youtu.be": "YouTube",
    "vk.com": "VK",
    "m.vk.com": "VK",
    "instagram.com": "Instagram",
    "www.instagram.com": "Instagram",
    "rutube.ru": "RuTube",
}


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
