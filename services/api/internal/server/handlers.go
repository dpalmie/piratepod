package server

import (
	"io"
	"net/http"
	"net/url"

	"github.com/piratepod/api/internal/auth"
)

func (h *Handler) healthz(w http.ResponseWriter, _ *http.Request) {
	w.Header().Set("Content-Type", "text/plain; charset=utf-8")
	_, _ = io.WriteString(w, "ok")
}

func (h *Handler) createJob(w http.ResponseWriter, r *http.Request) {
	h.proxy(w, r, http.MethodPost, "/orchestrate/jobs", true)
}

func (h *Handler) listJobs(w http.ResponseWriter, r *http.Request) {
	h.proxy(w, r, http.MethodGet, "/orchestrate/jobs", false)
}

func (h *Handler) getJob(w http.ResponseWriter, r *http.Request) {
	h.proxy(w, r, http.MethodGet, "/orchestrate/jobs/"+url.PathEscape(r.PathValue("id")), false)
}

func (h *Handler) retryJob(w http.ResponseWriter, r *http.Request) {
	h.proxy(w, r, http.MethodPost, "/orchestrate/jobs/"+url.PathEscape(r.PathValue("id"))+"/retry", false)
}

func (h *Handler) getFeed(w http.ResponseWriter, r *http.Request) {
	h.proxy(w, r, http.MethodGet, "/orchestrate/feed", false)
}

func (h *Handler) proxy(w http.ResponseWriter, r *http.Request, method, path string, withBody bool) {
	if _, ok := auth.OwnerFrom(r.Context()); !ok {
		http.Error(w, "unauthorized", http.StatusUnauthorized)
		return
	}
	var body []byte
	var err error
	contentType := ""
	if withBody {
		body, err = io.ReadAll(http.MaxBytesReader(w, r.Body, 1<<20))
		if err != nil {
			http.Error(w, "request body too large", http.StatusRequestEntityTooLarge)
			return
		}
		contentType = r.Header.Get("Content-Type")
		if contentType == "" {
			contentType = "application/json"
		}
	}
	resp, err := h.client.DoBytes(r.Context(), method, path, body, contentType)
	if err != nil {
		h.log.Error("orchestrate proxy", "path", path, "err", err)
		http.Error(w, err.Error(), http.StatusBadGateway)
		return
	}
	defer resp.Body.Close()
	if ct := resp.Header.Get("Content-Type"); ct != "" {
		w.Header().Set("Content-Type", ct)
	}
	w.WriteHeader(resp.StatusCode)
	_, _ = io.Copy(w, resp.Body)
}
