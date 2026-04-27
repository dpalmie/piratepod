-- +goose Up
CREATE TABLE jobs (
    id           TEXT PRIMARY KEY,
    owner_id     TEXT NOT NULL,
    status       TEXT NOT NULL,
    stage        TEXT NOT NULL,
    title        TEXT,
    urls_json    TEXT NOT NULL,
    result_json  TEXT,
    error        TEXT,
    created_at   TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    updated_at   TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    started_at   TEXT,
    finished_at  TEXT
);

CREATE INDEX jobs_owner_created_idx ON jobs(owner_id, created_at DESC);
CREATE INDEX jobs_status_created_idx ON jobs(status, created_at ASC);

CREATE TABLE job_events (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id     TEXT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    stage      TEXT NOT NULL,
    status     TEXT NOT NULL,
    message    TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

CREATE INDEX job_events_job_id_idx ON job_events(job_id, created_at ASC);

-- +goose Down
DROP INDEX IF EXISTS job_events_job_id_idx;
DROP TABLE IF EXISTS job_events;
DROP INDEX IF EXISTS jobs_status_created_idx;
DROP INDEX IF EXISTS jobs_owner_created_idx;
DROP TABLE IF EXISTS jobs;
