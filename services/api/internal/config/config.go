// Package config loads and validates runtime configuration from the environment.
package config

import (
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"strconv"
	"strings"
)

type Mode string

const (
	SelfHost Mode = "self_host"
	Managed  Mode = "managed"
)

type Config struct {
	Mode         Mode
	Port         int
	WebOrigin    string
	WorkspaceDir string

	SQLitePath string

	IngestURL      string
	ScriptgenURL   string
	AudiogenURL    string
	RSSURL         string
	OrchestrateURL string
	HTTPTimeout    int

	DefaultPodcastTitle       string
	DefaultPodcastDescription string
	DefaultPodcastAuthor      string
	DefaultPodcastLanguage    string
}

func Load() (*Config, error) {
	var errs []error
	cfg := &Config{Mode: Mode(getenv("PIRATEPOD_MODE", string(SelfHost)))}

	port, err := strconv.Atoi(getenv("PIRATEPOD_API_PORT", "8000"))
	if err != nil {
		errs = append(errs, fmt.Errorf("PIRATEPOD_API_PORT: %w", err))
	}
	cfg.Port = port

	timeout, err := strconv.Atoi(getenv("PIRATEPOD_API_HTTP_TIMEOUT", "120"))
	if err != nil {
		errs = append(errs, fmt.Errorf("PIRATEPOD_API_HTTP_TIMEOUT: %w", err))
	}
	cfg.HTTPTimeout = timeout

	cfg.WebOrigin = normalizeOriginList(getenv("PIRATEPOD_WEB_ORIGIN", "http://127.0.0.1:5173,http://localhost:5173"))
	cfg.WorkspaceDir = getenv("PIRATEPOD_WORKSPACE_DIR", "")
	if cfg.WorkspaceDir == "" {
		cfg.WorkspaceDir, err = detectWorkspaceDir()
		if err != nil {
			errs = append(errs, err)
		}
	} else {
		cfg.WorkspaceDir, err = filepath.Abs(cfg.WorkspaceDir)
		if err != nil {
			errs = append(errs, fmt.Errorf("PIRATEPOD_WORKSPACE_DIR: %w", err))
		}
	}
	cfg.IngestURL = strings.TrimRight(getenv("INGEST_URL", "http://localhost:8001"), "/")
	cfg.ScriptgenURL = strings.TrimRight(getenv("SCRIPTGEN_URL", "http://localhost:8002"), "/")
	cfg.AudiogenURL = strings.TrimRight(getenv("AUDIOGEN_URL", "http://localhost:8004"), "/")
	cfg.RSSURL = strings.TrimRight(getenv("RSS_URL", "http://localhost:8080"), "/")
	cfg.OrchestrateURL = strings.TrimRight(getenv("ORCHESTRATE_URL", "http://localhost:8003"), "/")
	cfg.DefaultPodcastTitle = getenv("PIRATEPOD_DEFAULT_TITLE", "PiratePod")
	cfg.DefaultPodcastDescription = getenv("PIRATEPOD_DEFAULT_DESCRIPTION", "Generated episodes from PiratePod")
	cfg.DefaultPodcastAuthor = getenv("PIRATEPOD_DEFAULT_AUTHOR", "")
	cfg.DefaultPodcastLanguage = getenv("PIRATEPOD_DEFAULT_LANGUAGE", "en")

	switch cfg.Mode {
	case SelfHost:
		cfg.SQLitePath = getenv("PIRATEPOD_API_SQLITE_PATH", "./data/piratepod-api.db")
		if cfg.SQLitePath == "" {
			errs = append(errs, errors.New("PIRATEPOD_API_SQLITE_PATH must be non-empty"))
		}
	case Managed:
		errs = append(errs, errors.New("PIRATEPOD_MODE=managed is not supported by the self-host API yet"))
	default:
		errs = append(errs, fmt.Errorf("PIRATEPOD_MODE: unknown mode %q", cfg.Mode))
	}

	if cfg.HTTPTimeout <= 0 {
		errs = append(errs, errors.New("PIRATEPOD_API_HTTP_TIMEOUT must be positive"))
	}
	if cfg.IngestURL == "" || cfg.ScriptgenURL == "" || cfg.AudiogenURL == "" || cfg.RSSURL == "" || cfg.OrchestrateURL == "" {
		errs = append(errs, errors.New("upstream service URLs must be non-empty"))
	}

	if err := errors.Join(errs...); err != nil {
		return nil, err
	}
	return cfg, nil
}

func getenv(key, def string) string {
	if v, ok := os.LookupEnv(key); ok && v != "" {
		return v
	}
	return def
}

func normalizeOriginList(value string) string {
	parts := strings.Split(value, ",")
	out := make([]string, 0, len(parts))
	for _, part := range parts {
		origin := strings.TrimRight(strings.TrimSpace(part), "/")
		if origin != "" {
			out = append(out, origin)
		}
	}
	return strings.Join(out, ",")
}

func detectWorkspaceDir() (string, error) {
	dir, err := os.Getwd()
	if err != nil {
		return "", fmt.Errorf("detect workspace: %w", err)
	}
	for {
		if fileExists(filepath.Join(dir, "pyproject.toml")) && fileExists(filepath.Join(dir, "justfile")) {
			return dir, nil
		}
		parent := filepath.Dir(dir)
		if parent == dir {
			return "", errors.New("PIRATEPOD_WORKSPACE_DIR is required when workspace root cannot be detected")
		}
		dir = parent
	}
}

func fileExists(path string) bool {
	info, err := os.Stat(path)
	return err == nil && !info.IsDir()
}
