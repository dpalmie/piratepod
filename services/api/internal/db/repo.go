package db

import (
	"context"
	"database/sql"
	"errors"
	"fmt"
	"time"
)

var ErrNotFound = errors.New("db: not found")

const (
	StatusQueued    = "queued"
	StatusRunning   = "running"
	StatusSucceeded = "succeeded"
	StatusFailed    = "failed"

	StageQueued  = "queued"
	StageIngest  = "ingest"
	StageScript  = "script"
	StageAudio   = "audio"
	StagePublish = "publish"
	StageDone    = "done"
)

type Job struct {
	ID         string
	OwnerID    string
	Status     string
	Stage      string
	Title      string
	URLsJSON   string
	ResultJSON string
	Error      string
	CreatedAt  time.Time
	UpdatedAt  time.Time
	StartedAt  *time.Time
	FinishedAt *time.Time
}

type JobEvent struct {
	ID        int64
	JobID     string
	Stage     string
	Status    string
	Message   string
	CreatedAt time.Time
}

type Repo struct{ db *sql.DB }

func NewRepo(db *sql.DB) *Repo { return &Repo{db: db} }

func (r *Repo) CreateJob(ctx context.Context, id, ownerID, title, urlsJSON string) (Job, error) {
	now := time.Now().UTC()
	_, err := r.db.ExecContext(ctx, `
        INSERT INTO jobs (id, owner_id, status, stage, title, urls_json, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)`,
		id, ownerID, StatusQueued, StageQueued, nullable(title), urlsJSON, formatTime(now), formatTime(now),
	)
	if err != nil {
		return Job{}, fmt.Errorf("db: create job: %w", err)
	}
	if err := r.AddEvent(ctx, id, StageQueued, StatusQueued, "job queued"); err != nil {
		return Job{}, err
	}
	return r.GetJob(ctx, id, ownerID)
}

func (r *Repo) GetJob(ctx context.Context, id, ownerID string) (Job, error) {
	row := r.db.QueryRowContext(ctx, `
        SELECT id, owner_id, status, stage, title, urls_json, result_json, error,
               created_at, updated_at, started_at, finished_at
        FROM jobs WHERE id = ? AND owner_id = ?`, id, ownerID)
	return scanJob(row)
}

func (r *Repo) ListJobs(ctx context.Context, ownerID string, limit int) ([]Job, error) {
	if limit <= 0 || limit > 100 {
		limit = 50
	}
	rows, err := r.db.QueryContext(ctx, `
        SELECT id, owner_id, status, stage, title, urls_json, result_json, error,
               created_at, updated_at, started_at, finished_at
        FROM jobs WHERE owner_id = ? ORDER BY created_at DESC LIMIT ?`, ownerID, limit)
	if err != nil {
		return nil, fmt.Errorf("db: list jobs: %w", err)
	}
	defer rows.Close()
	var out []Job
	for rows.Next() {
		j, err := scanJobRows(rows)
		if err != nil {
			return nil, err
		}
		out = append(out, j)
	}
	return out, rows.Err()
}

func (r *Repo) ListEvents(ctx context.Context, jobID string) ([]JobEvent, error) {
	rows, err := r.db.QueryContext(ctx, `
        SELECT id, job_id, stage, status, message, created_at
        FROM job_events WHERE job_id = ? ORDER BY created_at ASC, id ASC`, jobID)
	if err != nil {
		return nil, fmt.Errorf("db: list events: %w", err)
	}
	defer rows.Close()
	var out []JobEvent
	for rows.Next() {
		var e JobEvent
		var message sql.NullString
		var createdAt string
		if err := rows.Scan(&e.ID, &e.JobID, &e.Stage, &e.Status, &message, &createdAt); err != nil {
			return nil, fmt.Errorf("db: scan event: %w", err)
		}
		e.Message = message.String
		parsed, err := parseTime(createdAt)
		if err != nil {
			return nil, err
		}
		e.CreatedAt = parsed
		out = append(out, e)
	}
	return out, rows.Err()
}

func (r *Repo) AddEvent(ctx context.Context, jobID, stage, status, message string) error {
	_, err := r.db.ExecContext(ctx, `
        INSERT INTO job_events (job_id, stage, status, message, created_at)
        VALUES (?, ?, ?, ?, ?)`, jobID, stage, status, nullable(message), formatTime(time.Now().UTC()))
	if err != nil {
		return fmt.Errorf("db: add event: %w", err)
	}
	return nil
}

func (r *Repo) ClaimNextQueued(ctx context.Context) (*Job, error) {
	tx, err := r.db.BeginTx(ctx, nil)
	if err != nil {
		return nil, fmt.Errorf("db: begin claim: %w", err)
	}
	defer tx.Rollback()

	row := tx.QueryRowContext(ctx, `
        SELECT id, owner_id, status, stage, title, urls_json, result_json, error,
               created_at, updated_at, started_at, finished_at
        FROM jobs WHERE status = ? ORDER BY created_at ASC LIMIT 1`, StatusQueued)
	job, err := scanJob(row)
	if errors.Is(err, ErrNotFound) {
		return nil, nil
	}
	if err != nil {
		return nil, err
	}
	now := formatTime(time.Now().UTC())
	res, err := tx.ExecContext(ctx, `
        UPDATE jobs SET status = ?, stage = ?, error = NULL, started_at = COALESCE(started_at, ?), updated_at = ?
        WHERE id = ? AND status = ?`, StatusRunning, StageQueued, now, now, job.ID, StatusQueued)
	if err != nil {
		return nil, fmt.Errorf("db: claim job: %w", err)
	}
	n, _ := res.RowsAffected()
	if n == 0 {
		return nil, nil
	}
	if _, err := tx.ExecContext(ctx, `
        INSERT INTO job_events (job_id, stage, status, message, created_at)
        VALUES (?, ?, ?, ?, ?)`, job.ID, StageQueued, StatusRunning, "job started", now); err != nil {
		return nil, fmt.Errorf("db: add claim event: %w", err)
	}
	if err := tx.Commit(); err != nil {
		return nil, fmt.Errorf("db: commit claim: %w", err)
	}
	job.Status = StatusRunning
	job.Stage = StageQueued
	return &job, nil
}

func (r *Repo) SetRunningStage(ctx context.Context, jobID, stage, message string) error {
	now := formatTime(time.Now().UTC())
	_, err := r.db.ExecContext(ctx, `
        UPDATE jobs SET status = ?, stage = ?, error = NULL, updated_at = ? WHERE id = ?`,
		StatusRunning, stage, now, jobID)
	if err != nil {
		return fmt.Errorf("db: set stage: %w", err)
	}
	return r.AddEvent(ctx, jobID, stage, StatusRunning, message)
}

func (r *Repo) SetSucceeded(ctx context.Context, jobID, resultJSON string) error {
	now := formatTime(time.Now().UTC())
	_, err := r.db.ExecContext(ctx, `
        UPDATE jobs SET status = ?, stage = ?, result_json = ?, error = NULL, updated_at = ?, finished_at = ? WHERE id = ?`,
		StatusSucceeded, StageDone, resultJSON, now, now, jobID)
	if err != nil {
		return fmt.Errorf("db: set succeeded: %w", err)
	}
	return r.AddEvent(ctx, jobID, StageDone, StatusSucceeded, "job succeeded")
}

func (r *Repo) SetFailed(ctx context.Context, jobID, stage, message string) error {
	now := formatTime(time.Now().UTC())
	_, err := r.db.ExecContext(ctx, `
        UPDATE jobs SET status = ?, stage = ?, error = ?, updated_at = ?, finished_at = ? WHERE id = ?`,
		StatusFailed, stage, message, now, now, jobID)
	if err != nil {
		return fmt.Errorf("db: set failed: %w", err)
	}
	return r.AddEvent(ctx, jobID, stage, StatusFailed, message)
}

func (r *Repo) RetryJob(ctx context.Context, id, ownerID string) (Job, error) {
	job, err := r.GetJob(ctx, id, ownerID)
	if err != nil {
		return Job{}, err
	}
	if job.Status == StatusRunning || job.Status == StatusQueued {
		return job, nil
	}
	now := formatTime(time.Now().UTC())
	_, err = r.db.ExecContext(ctx, `
        UPDATE jobs SET status = ?, stage = ?, result_json = NULL, error = NULL, updated_at = ?, started_at = NULL, finished_at = NULL
        WHERE id = ? AND owner_id = ?`, StatusQueued, StageQueued, now, id, ownerID)
	if err != nil {
		return Job{}, fmt.Errorf("db: retry job: %w", err)
	}
	if err := r.AddEvent(ctx, id, StageQueued, StatusQueued, "job retried"); err != nil {
		return Job{}, err
	}
	return r.GetJob(ctx, id, ownerID)
}

func (r *Repo) ResetRunningToQueued(ctx context.Context) error {
	tx, err := r.db.BeginTx(ctx, nil)
	if err != nil {
		return fmt.Errorf("db: begin reset running jobs: %w", err)
	}
	defer tx.Rollback()

	rows, err := tx.QueryContext(ctx, `
        SELECT id, stage FROM jobs WHERE status = ?`, StatusRunning)
	if err != nil {
		return fmt.Errorf("db: list running jobs: %w", err)
	}
	type runningJob struct {
		id    string
		stage string
	}
	var jobs []runningJob
	for rows.Next() {
		var job runningJob
		if err := rows.Scan(&job.id, &job.stage); err != nil {
			_ = rows.Close()
			return fmt.Errorf("db: scan running job: %w", err)
		}
		jobs = append(jobs, job)
	}
	if err := rows.Close(); err != nil {
		return fmt.Errorf("db: close running jobs: %w", err)
	}
	if err := rows.Err(); err != nil {
		return fmt.Errorf("db: iterate running jobs: %w", err)
	}

	now := formatTime(time.Now().UTC())
	for _, job := range jobs {
		if job.stage == StagePublish {
			message := "job outcome unknown after restart during publish; retry may duplicate the episode"
			if _, err := tx.ExecContext(ctx, `
                UPDATE jobs SET status = ?, error = ?, updated_at = ?, finished_at = ?
                WHERE id = ? AND status = ?`,
				StatusFailed, message, now, now, job.id, StatusRunning); err != nil {
				return fmt.Errorf("db: fail publish-stage job: %w", err)
			}
			if _, err := tx.ExecContext(ctx, `
                INSERT INTO job_events (job_id, stage, status, message, created_at)
                VALUES (?, ?, ?, ?, ?)`, job.id, job.stage, StatusFailed, message, now); err != nil {
				return fmt.Errorf("db: add publish-stage reset event: %w", err)
			}
			continue
		}
		if _, err := tx.ExecContext(ctx, `
            UPDATE jobs SET status = ?, stage = ?, error = NULL, updated_at = ?, started_at = NULL, finished_at = NULL
            WHERE id = ? AND status = ?`, StatusQueued, StageQueued, now, job.id, StatusRunning); err != nil {
			return fmt.Errorf("db: reset running job: %w", err)
		}
		if _, err := tx.ExecContext(ctx, `
            INSERT INTO job_events (job_id, stage, status, message, created_at)
            VALUES (?, ?, ?, ?, ?)`, job.id, StageQueued, StatusQueued, "job reset to queued after restart", now); err != nil {
			return fmt.Errorf("db: add reset event: %w", err)
		}
	}
	if err := tx.Commit(); err != nil {
		return fmt.Errorf("db: commit reset running jobs: %w", err)
	}
	return nil
}

func scanJob(row *sql.Row) (Job, error) {
	var j Job
	var title, result, errText, startedAt, finishedAt sql.NullString
	var createdAt, updatedAt string
	err := row.Scan(&j.ID, &j.OwnerID, &j.Status, &j.Stage, &title, &j.URLsJSON, &result, &errText, &createdAt, &updatedAt, &startedAt, &finishedAt)
	if errors.Is(err, sql.ErrNoRows) {
		return Job{}, ErrNotFound
	}
	if err != nil {
		return Job{}, fmt.Errorf("db: scan job: %w", err)
	}
	return finishJobScan(j, title, result, errText, createdAt, updatedAt, startedAt, finishedAt)
}

func scanJobRows(rows *sql.Rows) (Job, error) {
	var j Job
	var title, result, errText, startedAt, finishedAt sql.NullString
	var createdAt, updatedAt string
	if err := rows.Scan(&j.ID, &j.OwnerID, &j.Status, &j.Stage, &title, &j.URLsJSON, &result, &errText, &createdAt, &updatedAt, &startedAt, &finishedAt); err != nil {
		return Job{}, fmt.Errorf("db: scan job: %w", err)
	}
	return finishJobScan(j, title, result, errText, createdAt, updatedAt, startedAt, finishedAt)
}

func finishJobScan(j Job, title, result, errText sql.NullString, createdAt, updatedAt string, startedAt, finishedAt sql.NullString) (Job, error) {
	j.Title = title.String
	j.ResultJSON = result.String
	j.Error = errText.String
	var err error
	j.CreatedAt, err = parseTime(createdAt)
	if err != nil {
		return Job{}, err
	}
	j.UpdatedAt, err = parseTime(updatedAt)
	if err != nil {
		return Job{}, err
	}
	if startedAt.Valid {
		t, err := parseTime(startedAt.String)
		if err != nil {
			return Job{}, err
		}
		j.StartedAt = &t
	}
	if finishedAt.Valid {
		t, err := parseTime(finishedAt.String)
		if err != nil {
			return Job{}, err
		}
		j.FinishedAt = &t
	}
	return j, nil
}

func parseTime(s string) (time.Time, error) {
	if t, err := time.Parse(time.RFC3339Nano, s); err == nil {
		return t, nil
	}
	if t, err := time.Parse("2006-01-02T15:04:05.000Z", s); err == nil {
		return t, nil
	}
	if t, err := time.Parse("2006-01-02 15:04:05", s); err == nil {
		return t, nil
	}
	return time.Time{}, fmt.Errorf("db: cannot parse time %q", s)
}

func formatTime(t time.Time) string { return t.UTC().Format(time.RFC3339Nano) }

func nullable(s string) any {
	if s == "" {
		return nil
	}
	return s
}
