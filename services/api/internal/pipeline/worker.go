package pipeline

import (
	"context"
	"encoding/json"
	"log/slog"
	"time"

	"github.com/piratepod/api/internal/db"
)

type Worker struct {
	repo   *db.Repo
	client *Client
	log    *slog.Logger
	wake   chan struct{}
}

func NewWorker(repo *db.Repo, client *Client, log *slog.Logger) *Worker {
	return &Worker{
		repo:   repo,
		client: client,
		log:    log,
		wake:   make(chan struct{}, 1),
	}
}

func (w *Worker) Wake() {
	select {
	case w.wake <- struct{}{}:
	default:
	}
}

func (w *Worker) Start(ctx context.Context) {
	go w.loop(ctx)
}

func (w *Worker) loop(ctx context.Context) {
	if err := w.repo.ResetRunningToQueued(ctx); err != nil {
		w.log.Error("reset running jobs", slog.Any("err", err))
	}
	ticker := time.NewTicker(time.Second)
	defer ticker.Stop()
	for {
		if err := w.drain(ctx); err != nil {
			w.log.Error("job drain", slog.Any("err", err))
		}
		select {
		case <-ctx.Done():
			return
		case <-w.wake:
		case <-ticker.C:
		}
	}
}

func (w *Worker) drain(ctx context.Context) error {
	for {
		job, err := w.repo.ClaimNextQueued(ctx)
		if err != nil || job == nil {
			return err
		}
		w.process(ctx, *job)
	}
}

func (w *Worker) process(ctx context.Context, job db.Job) {
	log := w.log.With(slog.String("job_id", job.ID))
	var req GenerateRequest
	if err := json.Unmarshal([]byte(job.URLsJSON), &req); err != nil {
		_ = w.repo.SetFailed(ctx, job.ID, db.StageQueued, "invalid stored job request")
		log.Error("decode job request", slog.Any("err", err))
		return
	}
	setStage := func(stage, message string) error {
		log.Info("job stage", slog.String("stage", stage), slog.String("message", message))
		return w.repo.SetRunningStage(ctx, job.ID, stage, message)
	}
	result, err := w.client.Generate(ctx, req, setStage)
	if err != nil {
		stage := db.StageQueued
		latest, getErr := w.repo.GetJob(ctx, job.ID, job.OwnerID)
		if getErr == nil {
			stage = latest.Stage
		}
		if setErr := w.repo.SetFailed(ctx, job.ID, stage, err.Error()); setErr != nil {
			log.Error("set failed", slog.Any("err", setErr))
		}
		log.Error("job failed", slog.Any("err", err))
		return
	}
	payload, err := json.Marshal(result)
	if err != nil {
		_ = w.repo.SetFailed(ctx, job.ID, db.StageDone, "failed to encode generation result")
		log.Error("encode result", slog.Any("err", err))
		return
	}
	if err := w.repo.SetSucceeded(ctx, job.ID, string(payload)); err != nil {
		log.Error("set succeeded", slog.Any("err", err))
		return
	}
	log.Info("job succeeded", slog.String("title", result.Title), slog.String("feed_url", result.FeedURL))
}
