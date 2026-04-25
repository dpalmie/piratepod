-- +goose Up
CREATE TABLE podcasts (
    id          TEXT PRIMARY KEY,
    owner_id    TEXT NOT NULL,
    slug        TEXT NOT NULL UNIQUE,
    title       TEXT NOT NULL,
    description TEXT,
    author      TEXT,
    cover_url   TEXT,
    language    TEXT NOT NULL DEFAULT 'en',
    created_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

CREATE TABLE episodes (
    id           TEXT PRIMARY KEY,
    podcast_id   TEXT NOT NULL REFERENCES podcasts(id) ON DELETE CASCADE,
    title        TEXT NOT NULL,
    description  TEXT,
    audio_url    TEXT NOT NULL,
    duration_sec INTEGER,
    guid         TEXT NOT NULL UNIQUE,
    published_at TEXT NOT NULL
);

CREATE INDEX episodes_podcast_id_idx ON episodes(podcast_id);

-- +goose Down
DROP INDEX IF EXISTS episodes_podcast_id_idx;
DROP TABLE IF EXISTS episodes;
DROP TABLE IF EXISTS podcasts;
