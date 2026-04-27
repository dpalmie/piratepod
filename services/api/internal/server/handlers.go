package server

import (
	"context"
	"encoding/json"
	"errors"
	"io"
	"net/http"
	"strings"
	"time"

	"github.com/google/uuid"

	"github.com/piratepod/api/internal/auth"
	"github.com/piratepod/api/internal/db"
	"github.com/piratepod/api/internal/pipeline"
)

type jobDTO struct {
	ID         string                   `json:"id"`
	Status     string                   `json:"status"`
	Stage      string                   `json:"stage"`
	Title      string                   `json:"title,omitempty"`
	URLs       []string                 `json:"urls"`
	Result     *pipeline.GenerateResult `json:"result,omitempty"`
	Error      string                   `json:"error,omitempty"`
	Events     []eventDTO               `json:"events,omitempty"`
	CreatedAt  string                   `json:"created_at"`
	UpdatedAt  string                   `json:"updated_at"`
	StartedAt  string                   `json:"started_at,omitempty"`
	FinishedAt string                   `json:"finished_at,omitempty"`
}

type eventDTO struct {
	ID        int64  `json:"id"`
	Stage     string `json:"stage"`
	Status    string `json:"status"`
	Message   string `json:"message,omitempty"`
	CreatedAt string `json:"created_at"`
}

func (h *Handler) healthz(w http.ResponseWriter, _ *http.Request) {
	w.Header().Set("Content-Type", "text/plain; charset=utf-8")
	_, _ = io.WriteString(w, "ok")
}

func (h *Handler) createJob(w http.ResponseWriter, r *http.Request) {
	ownerID, ok := auth.OwnerFrom(r.Context())
	if !ok {
		http.Error(w, "unauthorized", http.StatusUnauthorized)
		return
	}
	var req pipeline.GenerateRequest
	if err := json.NewDecoder(http.MaxBytesReader(w, r.Body, 1<<20)).Decode(&req); err != nil {
		http.Error(w, "invalid json", http.StatusBadRequest)
		return
	}
	req.URLs = cleanURLs(req.URLs)
	req.Title = strings.TrimSpace(req.Title)
	if len(req.URLs) == 0 {
		http.Error(w, "at least one URL is required", http.StatusBadRequest)
		return
	}
	payload, err := json.Marshal(req)
	if err != nil {
		h.serverError(w, "encode job", err)
		return
	}
	id, err := uuid.NewV7()
	if err != nil {
		h.serverError(w, "uuid", err)
		return
	}
	job, err := h.repo.CreateJob(r.Context(), id.String(), ownerID, req.Title, string(payload))
	if err != nil {
		h.serverError(w, "create job", err)
		return
	}
	if h.wake != nil {
		h.wake()
	}
	out, err := h.jobDTO(r.Context(), job, true)
	if err != nil {
		h.serverError(w, "load job events", err)
		return
	}
	writeJSON(w, http.StatusAccepted, out)
}

func (h *Handler) listJobs(w http.ResponseWriter, r *http.Request) {
	ownerID, ok := auth.OwnerFrom(r.Context())
	if !ok {
		http.Error(w, "unauthorized", http.StatusUnauthorized)
		return
	}
	jobs, err := h.repo.ListJobs(r.Context(), ownerID, 50)
	if err != nil {
		h.serverError(w, "list jobs", err)
		return
	}
	out := make([]jobDTO, 0, len(jobs))
	for _, job := range jobs {
		dto, err := h.jobDTO(r.Context(), job, false)
		if err != nil {
			h.serverError(w, "map job", err)
			return
		}
		out = append(out, dto)
	}
	writeJSON(w, http.StatusOK, out)
}

func (h *Handler) getJob(w http.ResponseWriter, r *http.Request) {
	ownerID, ok := auth.OwnerFrom(r.Context())
	if !ok {
		http.Error(w, "unauthorized", http.StatusUnauthorized)
		return
	}
	job, err := h.repo.GetJob(r.Context(), r.PathValue("id"), ownerID)
	if err != nil {
		if errors.Is(err, db.ErrNotFound) {
			http.NotFound(w, r)
			return
		}
		h.serverError(w, "get job", err)
		return
	}
	out, err := h.jobDTO(r.Context(), job, true)
	if err != nil {
		h.serverError(w, "load job events", err)
		return
	}
	writeJSON(w, http.StatusOK, out)
}

func (h *Handler) retryJob(w http.ResponseWriter, r *http.Request) {
	ownerID, ok := auth.OwnerFrom(r.Context())
	if !ok {
		http.Error(w, "unauthorized", http.StatusUnauthorized)
		return
	}
	job, err := h.repo.RetryJob(r.Context(), r.PathValue("id"), ownerID)
	if err != nil {
		if errors.Is(err, db.ErrNotFound) {
			http.NotFound(w, r)
			return
		}
		h.serverError(w, "retry job", err)
		return
	}
	if h.wake != nil {
		h.wake()
	}
	out, err := h.jobDTO(r.Context(), job, true)
	if err != nil {
		h.serverError(w, "load job events", err)
		return
	}
	writeJSON(w, http.StatusOK, out)
}

func (h *Handler) getFeed(w http.ResponseWriter, r *http.Request) {
	if _, ok := auth.OwnerFrom(r.Context()); !ok {
		http.Error(w, "unauthorized", http.StatusUnauthorized)
		return
	}
	feed, err := h.client.FetchFeed(r.Context())
	if err != nil {
		http.Error(w, err.Error(), http.StatusBadGateway)
		return
	}
	writeJSON(w, http.StatusOK, feed)
}

func (h *Handler) jobDTO(ctx context.Context, job db.Job, includeEvents bool) (jobDTO, error) {
	var req pipeline.GenerateRequest
	_ = json.Unmarshal([]byte(job.URLsJSON), &req)
	out := jobDTO{
		ID:        job.ID,
		Status:    job.Status,
		Stage:     job.Stage,
		Title:     job.Title,
		URLs:      req.URLs,
		Error:     job.Error,
		CreatedAt: job.CreatedAt.UTC().Format(timeFormat),
		UpdatedAt: job.UpdatedAt.UTC().Format(timeFormat),
	}
	if job.StartedAt != nil {
		out.StartedAt = job.StartedAt.UTC().Format(timeFormat)
	}
	if job.FinishedAt != nil {
		out.FinishedAt = job.FinishedAt.UTC().Format(timeFormat)
	}
	if job.ResultJSON != "" {
		var result pipeline.GenerateResult
		if err := json.Unmarshal([]byte(job.ResultJSON), &result); err == nil {
			out.Result = &result
		}
	}
	if includeEvents {
		events, err := h.repo.ListEvents(ctx, job.ID)
		if err != nil {
			return jobDTO{}, err
		}
		out.Events = make([]eventDTO, 0, len(events))
		for _, event := range events {
			out.Events = append(out.Events, eventDTO{
				ID:        event.ID,
				Stage:     event.Stage,
				Status:    event.Status,
				Message:   event.Message,
				CreatedAt: event.CreatedAt.UTC().Format(timeFormat),
			})
		}
	}
	return out, nil
}

func cleanURLs(urls []string) []string {
	out := make([]string, 0, len(urls))
	for _, u := range urls {
		if s := strings.TrimSpace(u); s != "" {
			out = append(out, s)
		}
	}
	return out
}

func (h *Handler) serverError(w http.ResponseWriter, op string, err error) {
	h.log.Error("handler", "op", op, "err", err)
	http.Error(w, "internal server error", http.StatusInternalServerError)
}

func writeJSON(w http.ResponseWriter, status int, v any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(v)
}

const timeFormat = time.RFC3339Nano
