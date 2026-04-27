package server

import (
	"net/http"
	"net/http/httptest"
	"testing"
)

func TestWithCORSAllowsConfiguredOrigins(t *testing.T) {
	handler := withCORS("http://127.0.0.1:5173,http://localhost:5173")(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusOK)
	}))

	for _, origin := range []string{"http://127.0.0.1:5173", "http://localhost:5173"} {
		t.Run(origin, func(t *testing.T) {
			req := httptest.NewRequest(http.MethodGet, "/feed", nil)
			req.Header.Set("Origin", origin)
			rr := httptest.NewRecorder()

			handler.ServeHTTP(rr, req)

			if got := rr.Header().Get("Access-Control-Allow-Origin"); got != origin {
				t.Fatalf("Access-Control-Allow-Origin = %q, want %q", got, origin)
			}
		})
	}
}

func TestWithCORSRejectsUnconfiguredOrigin(t *testing.T) {
	handler := withCORS("http://127.0.0.1:5173")(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusOK)
	}))
	req := httptest.NewRequest(http.MethodGet, "/feed", nil)
	req.Header.Set("Origin", "http://localhost:5173")
	rr := httptest.NewRecorder()

	handler.ServeHTTP(rr, req)

	if got := rr.Header().Get("Access-Control-Allow-Origin"); got != "" {
		t.Fatalf("Access-Control-Allow-Origin = %q, want empty", got)
	}
}
