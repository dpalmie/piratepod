import asyncio
import json
from collections.abc import Awaitable, Callable

from fastapi import HTTPException
from pydantic import ValidationError

from piratepod_core.logging import get_logger

from . import db
from .db import Job, JobRepo
from .schemas import GenerateRequest, GenerateResponse

Pipeline = Callable[
    [GenerateRequest, Callable[[str, str], Awaitable[None]]], Awaitable[GenerateResponse]
]

log = get_logger(__name__)


class JobWorker:
    def __init__(self, repo: JobRepo, pipeline: Pipeline, poll_interval: float = 1.0):
        self.repo = repo
        self.pipeline = pipeline
        self.poll_interval = poll_interval
        self._wake = asyncio.Event()
        self._task: asyncio.Task[None] | None = None

    def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        if self._task is None:
            return
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        self._task = None

    def wake(self) -> None:
        self._wake.set()

    async def _loop(self) -> None:
        try:
            await asyncio.to_thread(self.repo.reset_running_to_queued)
        except Exception as exc:
            log.error("orchestrate.reset_running.failed", err=str(exc))
        while True:
            try:
                await self._drain()
            except Exception as exc:
                log.error("orchestrate.drain.failed", err=str(exc))
            try:
                await asyncio.wait_for(self._wake.wait(), timeout=self.poll_interval)
                self._wake.clear()
            except TimeoutError:
                pass

    async def _drain(self) -> None:
        while True:
            job = await asyncio.to_thread(self.repo.claim_next_queued)
            if job is None:
                return
            await self._process(job)

    async def _process(self, job: Job) -> None:
        log.info("orchestrate.job.start", job_id=job.id)
        try:
            req = GenerateRequest.model_validate_json(job.urls_json)
        except ValidationError:
            await asyncio.to_thread(
                self.repo.set_failed,
                job.id,
                db.STAGE_QUEUED,
                "invalid stored job request",
            )
            return

        async def set_stage(stage: str, message: str) -> None:
            log.info("orchestrate.job.stage", job_id=job.id, stage=stage)
            await asyncio.to_thread(self.repo.set_running_stage, job.id, stage, message)

        try:
            result = await self.pipeline(req, set_stage)
        except Exception as exc:
            latest = await _latest_job(self.repo, job)
            await asyncio.to_thread(
                self.repo.set_failed,
                job.id,
                latest.stage,
                _error_message(exc),
            )
            log.error("orchestrate.job.failed", job_id=job.id, err=str(exc))
            return

        payload = result.model_dump_json()
        await asyncio.to_thread(self.repo.set_succeeded, job.id, payload)
        log.info("orchestrate.job.succeeded", job_id=job.id, title=result.title)


async def _latest_job(repo: JobRepo, fallback: Job) -> Job:
    try:
        return await asyncio.to_thread(repo.get_job, fallback.id, fallback.owner_id)
    except KeyError:
        return fallback


def _error_message(exc: Exception) -> str:
    if isinstance(exc, HTTPException):
        detail = exc.detail
        if isinstance(detail, str):
            return detail
        return json.dumps(detail)
    return str(exc) or exc.__class__.__name__
