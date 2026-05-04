package server

import (
	"encoding/json"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"github.com/piratepod/api/internal/auth"
	"github.com/piratepod/api/internal/config"
	"github.com/piratepod/api/internal/orchestrate"
)

func TestCreateJobProxiesToOrchestrate(t *testing.T) {
	var gotPath string
	var gotBody map[string]any
	upstream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		gotPath = r.URL.Path
		if r.Method != http.MethodPost {
			t.Fatalf("method = %s, want POST", r.Method)
		}
		if err := json.NewDecoder(r.Body).Decode(&gotBody); err != nil {
			t.Fatalf("decode body: %v", err)
		}
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusAccepted)
		_, _ = w.Write([]byte(`{"id":"job-1","status":"queued","stage":"queued","urls":["https://example.com/"],"created_at":"2026-01-01T00:00:00Z","updated_at":"2026-01-01T00:00:00Z"}`))
	}))
	defer upstream.Close()

	handler := New(testConfig(upstream.URL), orchestrate.NewClient(testConfig(upstream.URL)), auth.SelfAuth{}, slog.Default())
	req := httptest.NewRequest(http.MethodPost, "/jobs", strings.NewReader(`{"urls":["https://example.com"]}`))
	req.Header.Set("Content-Type", "application/json")
	rr := httptest.NewRecorder()

	handler.ServeHTTP(rr, req)

	if rr.Code != http.StatusAccepted {
		t.Fatalf("status = %d, want 202; body=%s", rr.Code, rr.Body.String())
	}
	if gotPath != "/orchestrate/jobs" {
		t.Fatalf("path = %q, want /orchestrate/jobs", gotPath)
	}
	if gotBody["urls"].([]any)[0] != "https://example.com" {
		t.Fatalf("unexpected proxied body: %#v", gotBody)
	}
}

func TestGetJobProxiesEscapedID(t *testing.T) {
	var gotPath string
	upstream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		gotPath = r.URL.EscapedPath()
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"id":"job 1","status":"queued","stage":"queued","urls":[],"created_at":"2026-01-01T00:00:00Z","updated_at":"2026-01-01T00:00:00Z"}`))
	}))
	defer upstream.Close()

	cfg := testConfig(upstream.URL)
	handler := New(cfg, orchestrate.NewClient(cfg), auth.SelfAuth{}, slog.Default())
	req := httptest.NewRequest(http.MethodGet, "/jobs/job%201", nil)
	rr := httptest.NewRecorder()

	handler.ServeHTTP(rr, req)

	if rr.Code != http.StatusOK {
		t.Fatalf("status = %d, want 200; body=%s", rr.Code, rr.Body.String())
	}
	if gotPath != "/orchestrate/jobs/job%201" {
		t.Fatalf("path = %q, want escaped job path", gotPath)
	}
}

func testConfig(orchestrateURL string) *config.Config {
	return &config.Config{
		Mode:           config.SelfHost,
		WebOrigin:      "http://127.0.0.1:5173",
		OrchestrateURL: orchestrateURL,
		HTTPTimeout:    int(time.Second.Seconds()),
	}
}
