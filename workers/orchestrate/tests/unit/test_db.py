from pathlib import Path

from orchestrate import db
from orchestrate.db import JobRepo, job_request_json


def repo(tmp_path: Path) -> JobRepo:
    r = JobRepo(tmp_path / "jobs.db")
    r.init()
    return r


def test_repo_create_list_claim_succeed_and_events(tmp_path: Path) -> None:
    r = repo(tmp_path)
    job = r.create_job(
        job_id="job-1",
        owner_id="self",
        title="Episode",
        urls_json=job_request_json(["https://example.com/"], "Episode"),
    )

    assert job.status == db.STATUS_QUEUED
    assert r.list_jobs("self")[0].id == "job-1"
    assert [event.message for event in r.list_events("job-1")] == ["job queued"]

    claimed = r.claim_next_queued()
    assert claimed is not None
    assert claimed.status == db.STATUS_RUNNING
    r.set_running_stage("job-1", db.STAGE_INGEST, "ingesting")
    r.set_succeeded("job-1", '{"title":"Episode"}')

    done = r.get_job("job-1", "self")
    assert done.status == db.STATUS_SUCCEEDED
    assert done.stage == db.STAGE_DONE
    assert done.result_json == '{"title":"Episode"}'
    assert [event.stage for event in r.list_events("job-1")] == [
        db.STAGE_QUEUED,
        db.STAGE_QUEUED,
        db.STAGE_INGEST,
        db.STAGE_DONE,
    ]


def test_repo_retry_resets_finished_job(tmp_path: Path) -> None:
    r = repo(tmp_path)
    r.create_job(
        job_id="job-1",
        owner_id="self",
        title="",
        urls_json=job_request_json(["https://example.com/"], None),
    )
    claimed = r.claim_next_queued()
    assert claimed is not None
    r.set_failed("job-1", db.STAGE_SCRIPT, "script failed")

    retried = r.retry_job("job-1", "self")

    assert retried.status == db.STATUS_QUEUED
    assert retried.stage == db.STAGE_QUEUED
    assert retried.error == ""
    assert r.list_events("job-1")[-1].message == "job retried"


def test_reset_running_to_queued_fails_publish_stage_jobs(tmp_path: Path) -> None:
    r = repo(tmp_path)
    r.create_job(
        job_id="publish-job",
        owner_id="self",
        title="",
        urls_json=job_request_json(["https://example.com/a"], None),
    )
    r.create_job(
        job_id="ingest-job",
        owner_id="self",
        title="",
        urls_json=job_request_json(["https://example.com/b"], None),
    )
    assert r.claim_next_queued() is not None
    r.set_running_stage("publish-job", db.STAGE_PUBLISH, "publishing")
    assert r.claim_next_queued() is not None
    r.set_running_stage("ingest-job", db.STAGE_INGEST, "ingesting")

    r.reset_running_to_queued()

    publish_job = r.get_job("publish-job", "self")
    assert publish_job.status == db.STATUS_FAILED
    assert publish_job.stage == db.STAGE_PUBLISH
    assert "retry may duplicate" in publish_job.error

    ingest_job = r.get_job("ingest-job", "self")
    assert ingest_job.status == db.STATUS_QUEUED
    assert ingest_job.stage == db.STAGE_QUEUED
