package config

import (
	"strings"
	"testing"
)

func TestLoadSelfHostDefaults(t *testing.T) {
	clearEnv(t)

	cfg, err := Load()
	if err != nil {
		t.Fatalf("Load: %v", err)
	}
	if cfg.Mode != SelfHost {
		t.Errorf("mode = %q, want self_host", cfg.Mode)
	}
	if cfg.Port != 8080 {
		t.Errorf("port = %d, want 8080", cfg.Port)
	}
	if cfg.BaseURL != "http://localhost:8080" {
		t.Errorf("base_url = %q", cfg.BaseURL)
	}
	if cfg.MediaURL != "http://localhost:8080/media" {
		t.Errorf("media_url = %q", cfg.MediaURL)
	}
	if cfg.SQLitePath == "" || cfg.MediaDir == "" {
		t.Errorf("sqlite_path / media_dir should have defaults, got %q / %q", cfg.SQLitePath, cfg.MediaDir)
	}
}

func TestLoadRejectsManagedModeForNow(t *testing.T) {
	clearEnv(t)
	t.Setenv("PIRATEPOD_MODE", "managed")

	_, err := Load()
	if err == nil {
		t.Fatal("expected error for managed mode in Phase 1")
	}
	if !strings.Contains(err.Error(), "not supported yet") {
		t.Errorf("unexpected error: %v", err)
	}
}

func TestLoadRejectsUnknownMode(t *testing.T) {
	clearEnv(t)
	t.Setenv("PIRATEPOD_MODE", "nope")

	_, err := Load()
	if err == nil {
		t.Fatal("expected error for unknown mode")
	}
	if !strings.Contains(err.Error(), "unknown mode") {
		t.Errorf("unexpected error: %v", err)
	}
}

func TestLoadHonorsExplicitURLs(t *testing.T) {
	clearEnv(t)
	t.Setenv("PIRATEPOD_BASE_URL", "https://feeds.example.com/")
	t.Setenv("PIRATEPOD_MEDIA_URL", "https://cdn.example.com/media/")

	cfg, err := Load()
	if err != nil {
		t.Fatalf("Load: %v", err)
	}
	if cfg.BaseURL != "https://feeds.example.com" {
		t.Errorf("base_url = %q", cfg.BaseURL)
	}
	if cfg.MediaURL != "https://cdn.example.com/media" {
		t.Errorf("media_url = %q", cfg.MediaURL)
	}
}

// clearEnv sets every config var to empty, which getenv treats as unset.
// t.Setenv registers cleanup so original values are restored post-test.
func clearEnv(t *testing.T) {
	t.Helper()
	for _, k := range []string{
		"PIRATEPOD_MODE", "PIRATEPOD_PORT", "PIRATEPOD_BASE_URL", "PIRATEPOD_MEDIA_URL",
		"PIRATEPOD_SQLITE_PATH", "PIRATEPOD_MEDIA_DIR",
	} {
		t.Setenv(k, "")
	}
}
