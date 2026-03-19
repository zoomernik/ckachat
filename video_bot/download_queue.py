from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from tempfile import TemporaryDirectory

from .config import Settings
from .models import DownloadResult
from .yt_client import YtDlpClient

logger = logging.getLogger(__name__)


@dataclass
class DownloadJob:
    user_id: int
    url: str
    platform: str
    format_id: str | None
    result_future: asyncio.Future[tuple[DownloadResult, TemporaryDirectory[str]]]


class DownloadQueue:
    def __init__(self, settings: Settings, client: YtDlpClient) -> None:
        self.settings = settings
        self.client = client
        self.queue: asyncio.Queue[DownloadJob] = asyncio.Queue()
        self._workers: list[asyncio.Task[None]] = []
        self._active_or_queued_users: set[int] = set()
        self._lock = asyncio.Lock()

    async def start(self) -> None:
        for idx in range(self.settings.max_parallel_downloads):
            task = asyncio.create_task(self._worker(idx + 1), name=f"dl-worker-{idx+1}")
            self._workers.append(task)

    async def stop(self) -> None:
        for task in self._workers:
            task.cancel()
        if self._workers:
            await asyncio.gather(*self._workers, return_exceptions=True)

    async def enqueue(self, user_id: int, url: str, platform: str, format_id: str | None) -> asyncio.Future[tuple[DownloadResult, TemporaryDirectory[str]]]:
        async with self._lock:
            if self.settings.per_user_single_active and user_id in self._active_or_queued_users:
                raise RuntimeError("already_active")
            self._active_or_queued_users.add(user_id)

        loop = asyncio.get_running_loop()
        future: asyncio.Future[tuple[DownloadResult, TemporaryDirectory[str]]] = loop.create_future()
        await self.queue.put(
            DownloadJob(
                user_id=user_id,
                url=url,
                platform=platform,
                format_id=format_id,
                result_future=future,
            )
        )
        return future

    async def _worker(self, worker_id: int) -> None:
        logger.info("Download worker %s started", worker_id)
        while True:
            job = await self.queue.get()
            try:
                result = await self._run_with_retries(job)
                if not job.result_future.done():
                    job.result_future.set_result(result)
            except Exception as exc:
                if not job.result_future.done():
                    job.result_future.set_exception(exc)
            finally:
                async with self._lock:
                    self._active_or_queued_users.discard(job.user_id)
                self.queue.task_done()

    def queued_count(self) -> int:
        return self.queue.qsize()

    async def _run_with_retries(
        self, job: DownloadJob
    ) -> tuple[DownloadResult, TemporaryDirectory[str]]:
        last_error: Exception | None = None
        for attempt in range(1, self.settings.max_download_attempts + 1):
            try:
                logger.info(
                    "Worker download attempt %s/%s for user=%s",
                    attempt,
                    self.settings.max_download_attempts,
                    job.user_id,
                )
                return await asyncio.wait_for(
                    self.client.download(
                        url=job.url,
                        platform=job.platform,
                        format_id=job.format_id,
                    ),
                    timeout=self.settings.job_timeout_seconds,
                )
            except Exception as exc:
                last_error = exc
                logger.warning(
                    "Download attempt %s failed for user=%s: %s",
                    attempt,
                    job.user_id,
                    exc,
                )
                if attempt < self.settings.max_download_attempts:
                    await asyncio.sleep(self.settings.retry_backoff_seconds * attempt)

        if last_error:
            raise last_error
        raise RuntimeError("Download failed with unknown error")
