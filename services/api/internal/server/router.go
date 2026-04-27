package server

import (
	"log/slog"
	"net/http"

	"github.com/piratepod/api/internal/auth"
	"github.com/piratepod/api/internal/config"
	"github.com/piratepod/api/internal/db"
	"github.com/piratepod/api/internal/pipeline"
)

type Handler struct {
	cfg    *config.Config
	repo   *db.Repo
	client *pipeline.Client
	wake   func()
	log    *slog.Logger
}

func New(cfg *config.Config, repo *db.Repo, client *pipeline.Client, authz auth.Authorizer, wake func(), log *slog.Logger) http.Handler {
	h := &Handler{cfg: cfg, repo: repo, client: client, wake: wake, log: log}
	mux := http.NewServeMux()
	mux.HandleFunc("GET /healthz", h.healthz)

	require := auth.RequireOwner(authz)
	mux.Handle("POST /jobs", require(http.HandlerFunc(h.createJob)))
	mux.Handle("GET /jobs", require(http.HandlerFunc(h.listJobs)))
	mux.Handle("GET /jobs/{id}", require(http.HandlerFunc(h.getJob)))
	mux.Handle("POST /jobs/{id}/retry", require(http.HandlerFunc(h.retryJob)))
	mux.Handle("GET /feed", require(http.HandlerFunc(h.getFeed)))

	return chain(mux, withCORS(cfg.WebOrigin), withRecover(log), withLogging(log))
}
