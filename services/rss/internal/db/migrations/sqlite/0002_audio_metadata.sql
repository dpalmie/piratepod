-- +goose Up
ALTER TABLE episodes ADD COLUMN audio_type TEXT NOT NULL DEFAULT 'audio/mpeg';
ALTER TABLE episodes ADD COLUMN audio_bytes INTEGER NOT NULL DEFAULT 0;

-- +goose Down
ALTER TABLE episodes DROP COLUMN audio_bytes;
ALTER TABLE episodes DROP COLUMN audio_type;
