package server

import (
	"crypto/rand"
	"encoding/base64"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"log/slog"
	"net/http"
	"net/url"
	"path/filepath"
	"strconv"
	"strings"
	"time"

	"github.com/google/uuid"

	"github.com/piratepod/rss/internal/auth"
	"github.com/piratepod/rss/internal/db"
	"github.com/piratepod/rss/internal/feed"
	"github.com/piratepod/rss/internal/storage"
)

const maxAudioBytes = 1 << 30 // 1 GiB; enough headroom for long-form audio

func (h *Handler) healthz(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Content-Type", "text/plain; charset=utf-8")
	_, _ = io.WriteString(w, "ok")
}

func (h *Handler) createPodcast(w http.ResponseWriter, r *http.Request) {
	ownerID, ok := auth.OwnerFrom(r.Context())
	if !ok {
		http.Error(w, "unauthorized", http.StatusUnauthorized)
		return
	}
	var body struct {
		Title       string `json:"title"`
		Description string `json:"description"`
		Author      string `json:"author"`
		CoverURL    string `json:"cover_url"`
		Language    string `json:"language"`
	}
	if err := json.NewDecoder(http.MaxBytesReader(w, r.Body, 1<<16)).Decode(&body); err != nil {
		http.Error(w, "invalid json", http.StatusBadRequest)
		return
	}
	if strings.TrimSpace(body.Title) == "" {
		http.Error(w, "title is required", http.StatusBadRequest)
		return
	}
	slug, err := newSlug()
	if err != nil {
		h.serverError(w, "slug", err)
		return
	}
	id, err := uuid.NewV7()
	if err != nil {
		h.serverError(w, "uuid", err)
		return
	}
	p, err := h.repo.CreatePodcast(r.Context(), db.Podcast{
		ID:          id.String(),
		OwnerID:     ownerID,
		Slug:        slug,
		Title:       body.Title,
		Description: body.Description,
		Author:      body.Author,
		CoverURL:    body.CoverURL,
		Language:    body.Language,
	})
	if err != nil {
		h.serverError(w, "create podcast", err)
		return
	}
	writeJSON(w, http.StatusCreated, podcastDTO(p, h.feedURL(p.Slug)))
}

func (h *Handler) listPodcasts(w http.ResponseWriter, r *http.Request) {
	ownerID, ok := auth.OwnerFrom(r.Context())
	if !ok {
		http.Error(w, "unauthorized", http.StatusUnauthorized)
		return
	}
	podcasts, err := h.repo.ListPodcastsByOwner(r.Context(), ownerID)
	if err != nil {
		h.serverError(w, "list podcasts", err)
		return
	}
	out := make([]map[string]any, 0, len(podcasts))
	for _, p := range podcasts {
		out = append(out, podcastDTO(p, h.feedURL(p.Slug)))
	}
	writeJSON(w, http.StatusOK, out)
}

func (h *Handler) deletePodcast(w http.ResponseWriter, r *http.Request) {
	ownerID, ok := auth.OwnerFrom(r.Context())
	if !ok {
		http.Error(w, "unauthorized", http.StatusUnauthorized)
		return
	}
	id := r.PathValue("id")
	if err := h.repo.DeletePodcast(r.Context(), id, ownerID); err != nil {
		if errors.Is(err, db.ErrNotFound) {
			http.NotFound(w, r)
			return
		}
		h.serverError(w, "delete podcast", err)
		return
	}
	w.WriteHeader(http.StatusNoContent)
}

func (h *Handler) createEpisode(w http.ResponseWriter, r *http.Request) {
	ownerID, ok := auth.OwnerFrom(r.Context())
	if !ok {
		http.Error(w, "unauthorized", http.StatusUnauthorized)
		return
	}
	podcastID := r.PathValue("id")
	p, err := h.repo.GetPodcastByID(r.Context(), podcastID)
	if err != nil {
		if errors.Is(err, db.ErrNotFound) {
			http.NotFound(w, r)
			return
		}
		h.serverError(w, "load podcast", err)
		return
	}
	if p.OwnerID != ownerID {
		http.NotFound(w, r) // don't leak existence
		return
	}
	if err := r.ParseMultipartForm(32 << 20); err != nil {
		http.Error(w, "invalid multipart", http.StatusBadRequest)
		return
	}
	title := strings.TrimSpace(r.FormValue("title"))
	if title == "" {
		http.Error(w, "title is required", http.StatusBadRequest)
		return
	}
	duration, _ := strconv.Atoi(r.FormValue("duration_sec"))
	file, header, err := r.FormFile("audio")
	if err != nil {
		http.Error(w, "audio file is required", http.StatusBadRequest)
		return
	}
	defer file.Close()
	if header.Size > maxAudioBytes {
		http.Error(w, "audio too large", http.StatusRequestEntityTooLarge)
		return
	}

	episodeID, err := uuid.NewV7()
	if err != nil {
		h.serverError(w, "uuid", err)
		return
	}
	audioType, ext, err := audioUploadType(header.Filename, header.Header.Get("Content-Type"))
	if err != nil {
		http.Error(w, err.Error(), http.StatusBadRequest)
		return
	}
	key := p.Slug + "/" + episodeID.String() + ext
	if err := h.store.Put(r.Context(), key, io.LimitReader(file, maxAudioBytes), audioType); err != nil {
		h.serverError(w, "store audio", err)
		return
	}
	audioURL := h.store.URLFor(r.Context(), key)

	episode, err := h.repo.CreateEpisode(r.Context(), db.Episode{
		ID:          episodeID.String(),
		PodcastID:   p.ID,
		Title:       title,
		Description: r.FormValue("description"),
		AudioURL:    audioURL,
		AudioType:   audioType,
		AudioBytes:  header.Size,
		DurationSec: duration,
		GUID:        episodeID.String(),
		PublishedAt: time.Now().UTC(),
	})
	if err != nil {
		h.serverError(w, "create episode", err)
		return
	}
	writeJSON(w, http.StatusCreated, episodeDTO(episode))
}

func (h *Handler) listEpisodes(w http.ResponseWriter, r *http.Request) {
	ownerID, ok := auth.OwnerFrom(r.Context())
	if !ok {
		http.Error(w, "unauthorized", http.StatusUnauthorized)
		return
	}
	podcastID := r.PathValue("id")
	p, err := h.repo.GetPodcastByID(r.Context(), podcastID)
	if err != nil {
		if errors.Is(err, db.ErrNotFound) {
			http.NotFound(w, r)
			return
		}
		h.serverError(w, "load podcast", err)
		return
	}
	if p.OwnerID != ownerID {
		http.NotFound(w, r)
		return
	}
	episodes, err := h.repo.ListEpisodesByPodcastID(r.Context(), podcastID)
	if err != nil {
		h.serverError(w, "list episodes", err)
		return
	}
	out := make([]map[string]any, 0, len(episodes))
	for _, episode := range episodes {
		out = append(out, episodeDTO(episode))
	}
	writeJSON(w, http.StatusOK, out)
}

func (h *Handler) getFeed(w http.ResponseWriter, r *http.Request) {
	slug := r.PathValue("slug")
	p, err := h.repo.GetPodcastBySlug(r.Context(), slug)
	if err != nil {
		if errors.Is(err, db.ErrNotFound) {
			http.NotFound(w, r)
			return
		}
		h.serverError(w, "load podcast", err)
		return
	}
	episodes, err := h.repo.ListEpisodesByPodcastID(r.Context(), p.ID)
	if err != nil {
		h.serverError(w, "list episodes", err)
		return
	}
	body, err := feed.Render(p, rewriteLocalMediaURLs(episodes, h.cfg.MediaURL), h.feedURL(p.Slug))
	if err != nil {
		h.serverError(w, "render feed", err)
		return
	}
	w.Header().Set("Content-Type", "application/rss+xml; charset=utf-8")
	_, _ = w.Write(body)
}

// getMedia serves self-host audio. In managed mode the feed XML points
// directly at the R2 CDN, so this handler is never hit.
func (h *Handler) getMedia(w http.ResponseWriter, r *http.Request) {
	key := r.PathValue("path")
	if key == "" {
		http.NotFound(w, r)
		return
	}
	rc, err := h.store.Open(r.Context(), key)
	if err != nil {
		if errors.Is(err, storage.ErrServedExternally) {
			http.NotFound(w, r)
			return
		}
		http.NotFound(w, r)
		return
	}
	defer rc.Close()
	http.ServeContent(w, r, key, time.Time{}, rc)
}

func (h *Handler) feedURL(slug string) string {
	return h.cfg.BaseURL + "/feeds/" + slug
}

func rewriteLocalMediaURLs(episodes []db.Episode, mediaURL string) []db.Episode {
	out := make([]db.Episode, len(episodes))
	for i, episode := range episodes {
		out[i] = episode
		out[i].AudioURL = rewriteLocalMediaURL(episode.AudioURL, mediaURL)
	}
	return out
}

func rewriteLocalMediaURL(audioURL, mediaURL string) string {
	u, err := url.Parse(audioURL)
	if err != nil || u.Scheme == "" || u.Host == "" {
		return audioURL
	}
	if !isLoopbackHost(u.Hostname()) || !strings.HasPrefix(u.Path, "/media/") {
		return audioURL
	}
	key := strings.TrimPrefix(u.Path, "/media/")
	return strings.TrimRight(mediaURL, "/") + "/" + strings.TrimLeft(key, "/")
}

func isLoopbackHost(host string) bool {
	switch strings.ToLower(host) {
	case "localhost", "127.0.0.1", "::1":
		return true
	default:
		return false
	}
}

func (h *Handler) serverError(w http.ResponseWriter, op string, err error) {
	h.log.Error("handler", slog.String("op", op), slog.Any("err", err))
	http.Error(w, "internal server error", http.StatusInternalServerError)
}

func writeJSON(w http.ResponseWriter, status int, v any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(v)
}

func newSlug() (string, error) {
	b := make([]byte, 8)
	if _, err := rand.Read(b); err != nil {
		return "", fmt.Errorf("slug: %w", err)
	}
	return base64.RawURLEncoding.EncodeToString(b), nil
}

func podcastDTO(p db.Podcast, feedURL string) map[string]any {
	return map[string]any{
		"id":          p.ID,
		"slug":        p.Slug,
		"title":       p.Title,
		"description": p.Description,
		"author":      p.Author,
		"cover_url":   p.CoverURL,
		"language":    p.Language,
		"feed_url":    feedURL,
		"created_at":  p.CreatedAt.UTC().Format(time.RFC3339),
	}
}

func episodeDTO(e db.Episode) map[string]any {
	return map[string]any{
		"id":           e.ID,
		"podcast_id":   e.PodcastID,
		"title":        e.Title,
		"description":  e.Description,
		"audio_url":    e.AudioURL,
		"audio_type":   e.AudioType,
		"audio_bytes":  e.AudioBytes,
		"duration_sec": e.DurationSec,
		"guid":         e.GUID,
		"published_at": e.PublishedAt.UTC().Format(time.RFC3339),
	}
}

func audioUploadType(filename, contentType string) (mimeType, ext string, err error) {
	ext = strings.ToLower(filepath.Ext(filename))
	contentType = strings.ToLower(strings.TrimSpace(strings.Split(contentType, ";")[0]))

	switch {
	case ext == ".wav" || contentType == "audio/wav" || contentType == "audio/x-wav" || contentType == "audio/wave":
		return "audio/wav", ".wav", nil
	case ext == ".mp3" || contentType == "audio/mpeg" || contentType == "audio/mp3":
		return "audio/mpeg", ".mp3", nil
	default:
		return "", "", fmt.Errorf("unsupported audio type %q for %q", contentType, filename)
	}
}
