// Package server wires the HTTP router, handlers, and middleware.
package server

import (
	"log/slog"
	"net/http"

	"github.com/piratepod/rss/internal/auth"
	"github.com/piratepod/rss/internal/config"
	"github.com/piratepod/rss/internal/db"
	"github.com/piratepod/rss/internal/storage"
)

type Handler struct {
	cfg   *config.Config
	repo  *db.Repo
	store storage.Storage
	log   *slog.Logger
}

func New(cfg *config.Config, repo *db.Repo, store storage.Storage, authz auth.Authorizer, log *slog.Logger) http.Handler {
	h := &Handler{cfg: cfg, repo: repo, store: store, log: log}

	mux := http.NewServeMux()

	mux.HandleFunc("GET /healthz", h.healthz)
	mux.HandleFunc("GET /feeds/{slug}", h.getFeed)
	mux.HandleFunc("GET /media/{path...}", h.getMedia)

	require := auth.RequireOwner(authz)
	mux.Handle("POST /podcasts", require(http.HandlerFunc(h.createPodcast)))
	mux.Handle("GET /podcasts", require(http.HandlerFunc(h.listPodcasts)))
	mux.Handle("GET /podcasts/{id}/episodes", require(http.HandlerFunc(h.listEpisodes)))
	mux.Handle("POST /podcasts/{id}/episodes", require(http.HandlerFunc(h.createEpisode)))
	mux.Handle("DELETE /podcasts/{id}", require(http.HandlerFunc(h.deletePodcast)))

	return chain(mux, withRecover(log), withLogging(log))
}
