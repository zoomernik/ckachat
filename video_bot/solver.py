from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SolverPayload:
    extractor_args: dict[str, dict[str, list[str]]] | None = None
    cookie_file: str | None = None


async def resolve_youtube_solver(
    mode: str,
    deno_bin: str,
    deno_solver_script: str | None,
    url: str,
) -> SolverPayload:
    if mode != "deno_ejs":
        return SolverPayload()

    if not deno_solver_script:
        logger.warning("YOUTUBE_SOLVER_MODE=deno_ejs, но DENO_SOLVER_SCRIPT не задан.")
        return SolverPayload()

    proc = await asyncio.create_subprocess_exec(
        deno_bin,
        "run",
        "-A",
        deno_solver_script,
        url,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    if proc.returncode != 0:
        logger.warning("Deno solver вернул ошибку: %s", stderr.decode(errors="ignore").strip())
        return SolverPayload()

    try:
        data = json.loads(stdout.decode("utf-8").strip() or "{}")
    except json.JSONDecodeError:
        logger.warning("Deno solver вернул не-JSON ответ")
        return SolverPayload()

    extractor_args = data.get("extractor_args")
    cookie_file = data.get("cookie_file")
    if extractor_args is not None and not isinstance(extractor_args, dict):
        extractor_args = None
    if cookie_file is not None and not isinstance(cookie_file, str):
        cookie_file = None

    return SolverPayload(extractor_args=extractor_args, cookie_file=cookie_file)
