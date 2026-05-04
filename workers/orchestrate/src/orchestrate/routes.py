import asyncio
import json
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request, status

from .db import Job, JobEvent, JobRepo, job_request_json
from .schemas import (
    FeedResponse,
    GenerateRequest,
    GenerateResponse,
    JobEventResponse,
    JobResponse,
)
from .service import fetch_feed, generate_podcast
from .worker import JobWorker

router = APIRouter()
OWNER_ID = "self"


@router.post("/orchestrate/generate", response_model=GenerateResponse)
async def orchestrate_generate(req: GenerateRequest) -> GenerateResponse:
    return await generate_podcast(req)


@router.post(
    "/orchestrate/jobs",
    response_model=JobResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_job(req: GenerateRequest, request: Request) -> JobResponse:
    repo = _repo(request)
    title = req.title.strip() if req.title else ""
    urls = [str(url) for url in req.urls]
    job = await asyncio.to_thread(
        repo.create_job,
        job_id=str(uuid4()),
        owner_id=OWNER_ID,
        title=title,
        urls_json=job_request_json(urls, title),
    )
    _worker(request).wake()
    return await _job_response(repo, job, include_events=True)


@router.get("/orchestrate/jobs", response_model=list[JobResponse])
async def list_jobs(request: Request) -> list[JobResponse]:
    repo = _repo(request)
    jobs = await asyncio.to_thread(repo.list_jobs, OWNER_ID, 50)
    return [await _job_response(repo, job, include_events=False) for job in jobs]


@router.get("/orchestrate/jobs/{job_id}", response_model=JobResponse)
async def get_job(job_id: str, request: Request) -> JobResponse:
    repo = _repo(request)
    try:
        job = await asyncio.to_thread(repo.get_job, job_id, OWNER_ID)
    except KeyError as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "job not found") from e
    return await _job_response(repo, job, include_events=True)


@router.post("/orchestrate/jobs/{job_id}/retry", response_model=JobResponse)
async def retry_job(job_id: str, request: Request) -> JobResponse:
    repo = _repo(request)
    try:
        job = await asyncio.to_thread(repo.retry_job, job_id, OWNER_ID)
    except KeyError as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "job not found") from e
    _worker(request).wake()
    return await _job_response(repo, job, include_events=True)


@router.get("/orchestrate/feed", response_model=FeedResponse)
async def orchestrate_feed() -> FeedResponse:
    return await fetch_feed()


def _repo(request: Request) -> JobRepo:
    return request.app.state.repo


def _worker(request: Request) -> JobWorker:
    return request.app.state.worker


async def _job_response(
    repo: JobRepo, job: Job, *, include_events: bool
) -> JobResponse:
    events = None
    if include_events:
        rows = await asyncio.to_thread(repo.list_events, job.id)
        events = [_event_response(event) for event in rows]
    data = json.loads(job.urls_json)
    result = None
    if job.result_json:
        result = json.loads(job.result_json)
    return JobResponse(
        id=job.id,
        status=job.status,
        stage=job.stage,
        title=job.title,
        urls=data.get("urls", []),
        result=result,
        error=job.error,
        events=events,
        created_at=job.created_at,
        updated_at=job.updated_at,
        started_at=job.started_at,
        finished_at=job.finished_at,
    )


def _event_response(event: JobEvent) -> JobEventResponse:
    return JobEventResponse(
        id=event.id,
        stage=event.stage,
        status=event.status,
        message=event.message,
        created_at=event.created_at,
    )
