// Package config loads and validates runtime configuration from the environment.
package config

import (
	"errors"
	"fmt"
	"os"
	"strconv"
	"strings"
)

type Mode string

const (
	SelfHost Mode = "self_host"
	Managed  Mode = "managed"
)

type Config struct {
	Mode     Mode
	Port     int
	BaseURL  string // public URL where feeds and (self-host only) media are served
	MediaURL string // public URL where media is served; may equal BaseURL/media

	// self-host
	SQLitePath string
	MediaDir   string

	// managed (Phase 2/3 — not loaded yet; kept here so the struct is stable)
	PostgresURL    string
	SupabaseURL    string
	StorageBackend string
}

// Load reads and validates configuration. Returns a multi-error listing every
// missing or invalid variable so operators can fix their env in one pass.

func Load() (*Config, error) {
	var errs []error

	cfg := &Config{
		Mode: Mode(getenv("PIRATEPOD_MODE", string(SelfHost))),
	}

	port, err := strconv.Atoi(getenv("PIRATEPOD_PORT", "8080"))
	if err != nil {
		errs = append(errs, fmt.Errorf("PIRATEPOD_PORT: %w", err))
	}
	cfg.Port = port

	cfg.BaseURL = strings.TrimRight(getenv("PIRATEPOD_BASE_URL", fmt.Sprintf("http://localhost:%d", port)), "/")
	cfg.MediaURL = strings.TrimRight(getenv("PIRATEPOD_MEDIA_URL", cfg.BaseURL+"/media"), "/")

	switch cfg.Mode {
	case SelfHost:
		errs = append(errs, loadSelfHost(cfg)...)
	case Managed:
		errs = append(errs, errors.New("PIRATEPOD_MODE=managed is not supported yet (Phase 2/3); see rss-plan.md"))
	default:
		errs = append(errs, fmt.Errorf("PIRATEPOD_MODE: unknown mode %q (expected self_host or managed)", cfg.Mode))
	}

	if err := errors.Join(errs...); err != nil {
		return nil, err
	}
	return cfg, nil
}

func loadSelfHost(cfg *Config) []error {
	var errs []error
	cfg.SQLitePath = getenv("PIRATEPOD_SQLITE_PATH", "./data/piratepod.db")
	cfg.MediaDir = getenv("PIRATEPOD_MEDIA_DIR", "./data/media")
	if cfg.SQLitePath == "" {
		errs = append(errs, errors.New("PIRATEPOD_SQLITE_PATH must be non-empty"))
	}
	if cfg.MediaDir == "" {
		errs = append(errs, errors.New("PIRATEPOD_MEDIA_DIR must be non-empty"))
	}
	return errs
}

func getenv(key, def string) string {
	if v, ok := os.LookupEnv(key); ok && v != "" {
		return v
	}
	return def
}
