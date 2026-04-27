// Package pipeline calls PiratePod worker services and the RSS service.
package pipeline

import (
	"bytes"
	"context"
	"encoding/binary"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"mime/multipart"
	"net/http"
	"net/url"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"sync"
	"time"

	"github.com/piratepod/api/internal/config"
	"github.com/piratepod/api/internal/db"
)

type Client struct {
	cfg       *config.Config
	http      *http.Client
	podcastMu sync.Mutex
}

type GenerateRequest struct {
	URLs  []string `json:"urls"`
	Title string   `json:"title,omitempty"`
}

type Source struct {
	Title    string `json:"title"`
	URL      string `json:"url"`
	Markdown string `json:"markdown"`
}

type GenerateResult struct {
	URLs            []string `json:"urls"`
	Sources         []Source `json:"sources"`
	Title           string   `json:"title"`
	Script          string   `json:"script"`
	AudioPath       string   `json:"audio_path"`
	AudioFormat     string   `json:"audio_format"`
	FeedURL         string   `json:"feed_url"`
	EpisodeID       string   `json:"episode_id"`
	EpisodeAudioURL string   `json:"episode_audio_url"`
}

type Podcast struct {
	ID          string `json:"id"`
	Slug        string `json:"slug"`
	Title       string `json:"title"`
	Description string `json:"description"`
	Author      string `json:"author"`
	CoverURL    string `json:"cover_url"`
	Language    string `json:"language"`
	FeedURL     string `json:"feed_url"`
	CreatedAt   string `json:"created_at"`
}

type Episode struct {
	ID          string `json:"id"`
	PodcastID   string `json:"podcast_id"`
	Title       string `json:"title"`
	Description string `json:"description"`
	AudioURL    string `json:"audio_url"`
	AudioType   string `json:"audio_type"`
	AudioBytes  int64  `json:"audio_bytes"`
	DurationSec int    `json:"duration_sec"`
	GUID        string `json:"guid"`
	PublishedAt string `json:"published_at"`
}

type Feed struct {
	Podcast  Podcast   `json:"podcast"`
	Episodes []Episode `json:"episodes"`
}

type StageFunc func(stage, message string) error

func NewClient(cfg *config.Config) *Client {
	return &Client{
		cfg:  cfg,
		http: &http.Client{Timeout: time.Duration(cfg.HTTPTimeout) * time.Second},
	}
}

func (c *Client) Generate(ctx context.Context, req GenerateRequest, setStage StageFunc) (GenerateResult, error) {
	urls, err := normalizeURLs(req.URLs)
	if err != nil {
		return GenerateResult{}, err
	}
	if err := setStage(db.StageIngest, "ingesting source URLs"); err != nil {
		return GenerateResult{}, err
	}
	sources, err := c.ingest(ctx, urls)
	if err != nil {
		return GenerateResult{}, err
	}

	title := episodeTitle(req.Title, sources)
	if err := setStage(db.StageScript, "generating podcast script"); err != nil {
		return GenerateResult{}, err
	}
	script, err := c.script(ctx, sources, title)
	if err != nil {
		return GenerateResult{}, err
	}

	if err := setStage(db.StageAudio, "generating audio"); err != nil {
		return GenerateResult{}, err
	}
	audio, err := c.audio(ctx, script, title)
	if err != nil {
		return GenerateResult{}, err
	}

	if err := setStage(db.StagePublish, "publishing episode to RSS"); err != nil {
		return GenerateResult{}, err
	}
	podcast, episode, err := c.publish(ctx, title, script, audio)
	if err != nil {
		return GenerateResult{}, err
	}

	return GenerateResult{
		URLs:            sourceURLs(sources),
		Sources:         sources,
		Title:           title,
		Script:          script,
		AudioPath:       audio.AudioPath,
		AudioFormat:     audio.AudioFormat,
		FeedURL:         podcast.FeedURL,
		EpisodeID:       episode.ID,
		EpisodeAudioURL: episode.AudioURL,
	}, nil
}

func (c *Client) FetchFeed(ctx context.Context) (Feed, error) {
	podcast, err := c.selfHostPodcast(ctx)
	if err != nil {
		return Feed{}, err
	}
	var episodes []Episode
	if err := c.doJSON(ctx, http.MethodGet, c.cfg.RSSURL+"/podcasts/"+url.PathEscape(podcast.ID)+"/episodes", nil, &episodes); err != nil {
		return Feed{}, fmt.Errorf("rss list episodes: %w", err)
	}
	return Feed{Podcast: podcast, Episodes: episodes}, nil
}

func (c *Client) ingest(ctx context.Context, urls []string) ([]Source, error) {
	sources := make([]Source, 0, len(urls))
	for _, sourceURL := range urls {
		var out Source
		if err := c.doJSON(ctx, http.MethodPost, c.cfg.IngestURL+"/ingest/url", map[string]string{"url": sourceURL}, &out); err != nil {
			return nil, fmt.Errorf("ingest %s: %w", sourceURL, err)
		}
		sources = append(sources, out)
	}
	return sources, nil
}

func (c *Client) script(ctx context.Context, sources []Source, title string) (string, error) {
	var out struct {
		Script string `json:"script"`
	}
	body := struct {
		Title   string   `json:"title"`
		Sources []Source `json:"sources"`
	}{Title: title, Sources: sources}
	if err := c.doJSON(ctx, http.MethodPost, c.cfg.ScriptgenURL+"/scriptgen/script", body, &out); err != nil {
		return "", fmt.Errorf("scriptgen: %w", err)
	}
	if strings.TrimSpace(out.Script) == "" {
		return "", errors.New("scriptgen returned empty script")
	}
	return out.Script, nil
}

type audioResponse struct {
	AudioPath   string `json:"audio_path"`
	AudioFormat string `json:"audio_format"`
}

func (c *Client) audio(ctx context.Context, script, title string) (audioResponse, error) {
	var out audioResponse
	body := map[string]string{"script": script, "title": title}
	if err := c.doJSON(ctx, http.MethodPost, c.cfg.AudiogenURL+"/audiogen/audio", body, &out); err != nil {
		return audioResponse{}, fmt.Errorf("audiogen: %w", err)
	}
	if out.AudioFormat == "" {
		out.AudioFormat = "wav"
	}
	if strings.TrimSpace(out.AudioPath) == "" {
		return audioResponse{}, errors.New("audiogen returned empty audio_path")
	}
	return out, nil
}

func (c *Client) publish(ctx context.Context, title, script string, audio audioResponse) (Podcast, Episode, error) {
	podcast, err := c.selfHostPodcast(ctx)
	if err != nil {
		return Podcast{}, Episode{}, err
	}
	episode, err := c.publishEpisode(ctx, podcast.ID, title, script, audio)
	if err != nil {
		return Podcast{}, Episode{}, err
	}
	return podcast, episode, nil
}

func (c *Client) selfHostPodcast(ctx context.Context) (Podcast, error) {
	c.podcastMu.Lock()
	defer c.podcastMu.Unlock()

	var podcasts []Podcast
	if err := c.doJSON(ctx, http.MethodGet, c.cfg.RSSURL+"/podcasts", nil, &podcasts); err != nil {
		return Podcast{}, fmt.Errorf("rss list podcasts: %w", err)
	}
	if len(podcasts) == 1 {
		return podcasts[0], nil
	}
	if len(podcasts) > 1 {
		return Podcast{}, fmt.Errorf("rss self-host expected exactly one podcast, found %d", len(podcasts))
	}
	return c.createPodcast(ctx)
}

func (c *Client) createPodcast(ctx context.Context) (Podcast, error) {
	body := map[string]string{
		"title":       c.cfg.DefaultPodcastTitle,
		"description": c.cfg.DefaultPodcastDescription,
		"author":      c.cfg.DefaultPodcastAuthor,
		"language":    c.cfg.DefaultPodcastLanguage,
	}
	var out Podcast
	if err := c.doJSON(ctx, http.MethodPost, c.cfg.RSSURL+"/podcasts", body, &out); err != nil {
		return Podcast{}, fmt.Errorf("rss create podcast: %w", err)
	}
	return out, nil
}

func (c *Client) publishEpisode(ctx context.Context, podcastID, title, script string, audio audioResponse) (Episode, error) {
	path := c.resolveAudioPath(audio.AudioPath)
	duration := wavDurationSec(path)

	contentType, err := audioContentType(audio.AudioFormat, filepath.Ext(path))
	if err != nil {
		return Episode{}, err
	}

	bodyReader, bodyWriter := io.Pipe()
	writer := multipart.NewWriter(bodyWriter)
	writeErr := make(chan error, 1)
	go func() {
		err := writeEpisodeMultipart(writer, path, title, script, duration)
		if err != nil {
			_ = bodyWriter.CloseWithError(err)
			writeErr <- err
			return
		}
		writeErr <- bodyWriter.Close()
	}()

	req, err := http.NewRequestWithContext(ctx, http.MethodPost, c.cfg.RSSURL+"/podcasts/"+url.PathEscape(podcastID)+"/episodes", bodyReader)
	if err != nil {
		_ = bodyReader.CloseWithError(err)
		<-writeErr
		return Episode{}, err
	}
	req.Header.Set("Content-Type", writer.FormDataContentType())
	req.Header.Set("X-PiratePod-Audio-Type", contentType)
	resp, err := c.http.Do(req)
	if err != nil {
		_ = bodyReader.CloseWithError(err)
		<-writeErr
		return Episode{}, err
	}
	defer resp.Body.Close()
	if err := <-writeErr; err != nil {
		return Episode{}, fmt.Errorf("write episode multipart: %w", err)
	}
	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		b, _ := io.ReadAll(io.LimitReader(resp.Body, 4096))
		return Episode{}, fmt.Errorf("rss create episode: status %d: %s", resp.StatusCode, strings.TrimSpace(string(b)))
	}
	var out Episode
	if err := json.NewDecoder(resp.Body).Decode(&out); err != nil {
		return Episode{}, fmt.Errorf("decode rss episode: %w", err)
	}
	return out, nil
}

func writeEpisodeMultipart(writer *multipart.Writer, audioPath, title, script string, duration int) error {
	if err := writer.WriteField("title", title); err != nil {
		return err
	}
	if err := writer.WriteField("description", script); err != nil {
		return err
	}
	if duration > 0 {
		if err := writer.WriteField("duration_sec", strconv.Itoa(duration)); err != nil {
			return err
		}
	}
	file, err := os.Open(audioPath)
	if err != nil {
		return fmt.Errorf("open generated audio %q: %w", audioPath, err)
	}
	defer file.Close()
	part, err := writer.CreateFormFile("audio", filepath.Base(audioPath))
	if err != nil {
		return err
	}
	if _, err := io.Copy(part, file); err != nil {
		return err
	}
	return writer.Close()
}

func (c *Client) resolveAudioPath(audioPath string) string {
	path := filepath.Clean(audioPath)
	if filepath.IsAbs(path) {
		return path
	}
	return filepath.Join(c.cfg.WorkspaceDir, path)
}

func (c *Client) doJSON(ctx context.Context, method, endpoint string, body any, out any) error {
	var reader io.Reader
	if body != nil {
		b, err := json.Marshal(body)
		if err != nil {
			return err
		}
		reader = bytes.NewReader(b)
	}
	req, err := http.NewRequestWithContext(ctx, method, endpoint, reader)
	if err != nil {
		return err
	}
	if body != nil {
		req.Header.Set("Content-Type", "application/json")
	}
	resp, err := c.http.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		b, _ := io.ReadAll(io.LimitReader(resp.Body, 4096))
		return fmt.Errorf("status %d: %s", resp.StatusCode, strings.TrimSpace(string(b)))
	}
	if out == nil {
		return nil
	}
	if err := json.NewDecoder(resp.Body).Decode(out); err != nil {
		return fmt.Errorf("decode json: %w", err)
	}
	return nil
}

func normalizeURLs(raw []string) ([]string, error) {
	out := make([]string, 0, len(raw))
	seen := map[string]struct{}{}
	for _, item := range raw {
		s := strings.TrimSpace(item)
		if s == "" {
			continue
		}
		if !strings.Contains(s, "://") {
			s = "https://" + s
		}
		u, err := url.ParseRequestURI(s)
		if err != nil || u.Scheme == "" || u.Host == "" {
			return nil, fmt.Errorf("invalid url %q", item)
		}
		if u.Scheme != "http" && u.Scheme != "https" {
			return nil, fmt.Errorf("unsupported url scheme %q", u.Scheme)
		}
		normalized := u.String()
		if _, ok := seen[normalized]; ok {
			continue
		}
		seen[normalized] = struct{}{}
		out = append(out, normalized)
	}
	if len(out) == 0 {
		return nil, errors.New("at least one URL is required")
	}
	return out, nil
}

func episodeTitle(requestTitle string, sources []Source) string {
	if title := strings.TrimSpace(requestTitle); title != "" {
		return title
	}
	if len(sources) == 1 {
		return sources[0].Title
	}
	return fmt.Sprintf("Digest: %s + %d more", sources[0].Title, len(sources)-1)
}

func sourceURLs(sources []Source) []string {
	out := make([]string, 0, len(sources))
	for _, source := range sources {
		out = append(out, source.URL)
	}
	return out
}

// wavDurationSec parses a minimal RIFF/WAVE header and returns floor(seconds).
// Returns 0 if the file isn't a WAV we can interpret; callers treat 0 as "unknown".
func wavDurationSec(path string) int {
	f, err := os.Open(path)
	if err != nil {
		return 0
	}
	defer f.Close()

	var hdr [12]byte
	if _, err := io.ReadFull(f, hdr[:]); err != nil {
		return 0
	}
	if string(hdr[0:4]) != "RIFF" || string(hdr[8:12]) != "WAVE" {
		return 0
	}

	var byteRate uint32
	for {
		var ch [8]byte
		if _, err := io.ReadFull(f, ch[:]); err != nil {
			return 0
		}
		size := binary.LittleEndian.Uint32(ch[4:8])
		switch string(ch[0:4]) {
		case "fmt ":
			buf := make([]byte, size)
			if _, err := io.ReadFull(f, buf); err != nil {
				return 0
			}
			if len(buf) >= 12 {
				byteRate = binary.LittleEndian.Uint32(buf[8:12])
			}
		case "data":
			if byteRate == 0 {
				return 0
			}
			return int(size / byteRate)
		default:
			if _, err := f.Seek(int64(size), io.SeekCurrent); err != nil {
				return 0
			}
		}
		if size%2 == 1 {
			if _, err := f.Seek(1, io.SeekCurrent); err != nil {
				return 0
			}
		}
	}
}

func audioContentType(audioFormat, suffix string) (string, error) {
	format := strings.ToLower(strings.Trim(strings.TrimSpace(audioFormat), "."))
	ext := strings.ToLower(strings.Trim(strings.TrimSpace(suffix), "."))
	switch {
	case format == "wav" || ext == "wav":
		return "audio/wav", nil
	case format == "mp3" || ext == "mp3":
		return "audio/mpeg", nil
	default:
		return "", fmt.Errorf("unsupported generated audio format %q", audioFormat)
	}
}
