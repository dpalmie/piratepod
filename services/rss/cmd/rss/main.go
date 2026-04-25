// Command rss is the PiratePod rss service entrypoint.
package main

import (
	"context"
	"errors"
	"fmt"
	"log/slog"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/piratepod/rss/internal/auth"
	"github.com/piratepod/rss/internal/config"
	"github.com/piratepod/rss/internal/db"
	"github.com/piratepod/rss/internal/server"
	"github.com/piratepod/rss/internal/storage"
)

func main() {
	if err := run(); err != nil {
		fmt.Fprintln(os.Stderr, "fatal:", err)
		os.Exit(1)
	}
}

func run() error {
	cfg, err := config.Load()
	if err != nil {
		return err
	}

	log := newLogger(cfg)
	log.Info("starting rss service",
		slog.String("mode", string(cfg.Mode)),
		slog.Int("port", cfg.Port),
		slog.String("base_url", cfg.BaseURL),
	)

	database, err := db.OpenSQLite(cfg.SQLitePath)
	if err != nil {
		return err
	}
	defer database.Close()

	store, err := storage.NewLocal(cfg.MediaDir, cfg.MediaURL)
	if err != nil {
		return err
	}

	repo := db.NewRepo(database)
	authz := auth.SelfAuth{}

	srv := &http.Server{
		Addr:              fmt.Sprintf(":%d", cfg.Port),
		Handler:           server.New(cfg, repo, store, authz, log),
		ReadHeaderTimeout: 10 * time.Second,
	}

	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()

	errCh := make(chan error, 1)
	go func() {
		log.Info("listening", slog.String("addr", srv.Addr))
		if err := srv.ListenAndServe(); err != nil && !errors.Is(err, http.ErrServerClosed) {
			errCh <- err
		}
		close(errCh)
	}()

	select {
	case err := <-errCh:
		return err
	case <-ctx.Done():
		log.Info("shutting down")
	}

	shutdownCtx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	return srv.Shutdown(shutdownCtx)
}

func newLogger(cfg *config.Config) *slog.Logger {
	opts := &slog.HandlerOptions{Level: slog.LevelInfo}
	if cfg.Mode == config.Managed {
		return slog.New(slog.NewJSONHandler(os.Stdout, opts))
	}
	return slog.New(slog.NewTextHandler(os.Stdout, opts))
}
