import asyncio
from pathlib import Path

from orchestrate import db
from orchestrate.db import JobRepo, job_request_json
from orchestrate.schemas import GenerateRequest, GenerateResponse
from orchestrate.worker import JobWorker


def repo(tmp_path: Path) -> JobRepo:
    r = JobRepo(tmp_path / "jobs.db")
    r.init()
    return r


def test_worker_processes_queued_job_and_records_progress(tmp_path: Path) -> None:
    r = repo(tmp_path)
    r.create_job(
        job_id="job-1",
        owner_id="self",
        title="Episode",
        urls_json=job_request_json(["https://example.com/"], "Episode"),
    )
    seen_stages: list[str] = []

    async def pipeline(req: GenerateRequest, set_stage):
        assert [str(url) for url in req.urls] == ["https://example.com/"]
        await set_stage(db.STAGE_INGEST, "ingesting")
        seen_stages.append(db.STAGE_INGEST)
        return GenerateResponse(
            urls=["https://example.com/"],
            sources=[
                {
                    "title": "Example",
                    "url": "https://example.com/",
                    "markdown": "Body",
                }
            ],
            title="Episode",
            script="Script",
            audio_path=".piratepod/audio/episode.wav",
            audio_format="wav",
            feed_url="http://localhost:8080/feeds/feed",
            episode_id="episode-1",
            episode_audio_url="http://localhost:8080/media/feed/episode-1.wav",
        )

    worker = JobWorker(r, pipeline)

    asyncio.run(worker._drain())

    job = r.get_job("job-1", "self")
    assert job.status == db.STATUS_SUCCEEDED
    assert job.stage == db.STAGE_DONE
    assert seen_stages == [db.STAGE_INGEST]
    assert [event.stage for event in r.list_events("job-1")] == [
        db.STAGE_QUEUED,
        db.STAGE_QUEUED,
        db.STAGE_INGEST,
        db.STAGE_DONE,
    ]


def test_worker_marks_job_failed_on_pipeline_error(tmp_path: Path) -> None:
    r = repo(tmp_path)
    r.create_job(
        job_id="job-1",
        owner_id="self",
        title="",
        urls_json=job_request_json(["https://example.com/"], None),
    )

    async def pipeline(_req: GenerateRequest, set_stage):
        await set_stage(db.STAGE_SCRIPT, "generating script")
        raise RuntimeError("boom")

    worker = JobWorker(r, pipeline)

    asyncio.run(worker._drain())

    job = r.get_job("job-1", "self")
    assert job.status == db.STATUS_FAILED
    assert job.stage == db.STAGE_SCRIPT
    assert job.error == "boom"
