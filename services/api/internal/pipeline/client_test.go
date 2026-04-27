package pipeline

import (
	"bytes"
	"context"
	"encoding/binary"
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"github.com/piratepod/api/internal/config"
)

func TestNormalizeURLsAddsSchemeAndDedupes(t *testing.T) {
	got, err := normalizeURLs([]string{"example.com", "https://example.com", " http://example.org/path "})
	if err != nil {
		t.Fatalf("normalizeURLs: %v", err)
	}
	want := []string{"https://example.com", "http://example.org/path"}
	if len(got) != len(want) {
		t.Fatalf("got %v, want %v", got, want)
	}
	for i := range want {
		if got[i] != want[i] {
			t.Fatalf("got %v, want %v", got, want)
		}
	}
}

func TestNormalizeURLsRejectsUnsupportedScheme(t *testing.T) {
	if _, err := normalizeURLs([]string{"ftp://example.com/file"}); err == nil {
		t.Fatal("expected unsupported scheme error")
	}
}

func TestEpisodeTitle(t *testing.T) {
	sources := []Source{{Title: "First"}, {Title: "Second"}}
	if got := episodeTitle("Manual", sources); got != "Manual" {
		t.Fatalf("got %q, want Manual", got)
	}
	if got := episodeTitle("", sources[:1]); got != "First" {
		t.Fatalf("got %q, want First", got)
	}
	if got := episodeTitle("", sources); got != "Digest: First + 1 more" {
		t.Fatalf("got %q, want digest title", got)
	}
}

func TestAudioContentType(t *testing.T) {
	if got, err := audioContentType("wav", ".wav"); err != nil || got != "audio/wav" {
		t.Fatalf("got %q/%v, want audio/wav", got, err)
	}
	if got, err := audioContentType("mp3", ".mp3"); err != nil || got != "audio/mpeg" {
		t.Fatalf("got %q/%v, want audio/mpeg", got, err)
	}
	if _, err := audioContentType("flac", ".flac"); err == nil {
		t.Fatal("expected unsupported format error")
	}
}

func TestResolveAudioPathUsesWorkspaceForRelativePath(t *testing.T) {
	client := NewClient(&config.Config{WorkspaceDir: "/workspace", HTTPTimeout: 1})

	got := client.resolveAudioPath(".piratepod/audio/foo.wav")
	want := filepath.Join("/workspace", ".piratepod/audio/foo.wav")
	if got != want {
		t.Fatalf("got %q, want %q", got, want)
	}
}

func TestResolveAudioPathPreservesAbsolutePath(t *testing.T) {
	client := NewClient(&config.Config{WorkspaceDir: "/workspace", HTTPTimeout: 1})
	path := filepath.Join(string(filepath.Separator), "tmp", "foo.wav")

	if got := client.resolveAudioPath(path); got != path {
		t.Fatalf("got %q, want %q", got, path)
	}
}

func TestWavDurationSec(t *testing.T) {
	path := writeTestWAV(t, 3)

	if got := wavDurationSec(path); got != 3 {
		t.Fatalf("got %d, want 3", got)
	}
}

func TestWavDurationSecReturnsZeroForInvalidFile(t *testing.T) {
	path := filepath.Join(t.TempDir(), "bad.wav")
	if err := os.WriteFile(path, []byte("not wav"), 0o644); err != nil {
		t.Fatalf("write bad wav: %v", err)
	}

	if got := wavDurationSec(path); got != 0 {
		t.Fatalf("got %d, want 0", got)
	}
}

func TestPublishEpisodeSendsDurationSec(t *testing.T) {
	audioPath := writeTestWAV(t, 4)
	var gotDuration string
	var gotTitle string
	var gotDescription string
	var gotFilename string

	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			t.Fatalf("got method %s, want POST", r.Method)
		}
		if r.URL.Path != "/podcasts/podcast-1/episodes" {
			t.Fatalf("got path %s", r.URL.Path)
		}
		if !strings.HasPrefix(r.Header.Get("Content-Type"), "multipart/form-data") {
			t.Fatalf("got content type %q, want multipart", r.Header.Get("Content-Type"))
		}
		if err := r.ParseMultipartForm(1 << 20); err != nil {
			t.Fatalf("parse multipart: %v", err)
		}
		gotDuration = r.FormValue("duration_sec")
		gotTitle = r.FormValue("title")
		gotDescription = r.FormValue("description")
		file, header, err := r.FormFile("audio")
		if err != nil {
			t.Fatalf("form file: %v", err)
		}
		defer file.Close()
		gotFilename = header.Filename
		if _, err := io.Copy(io.Discard, file); err != nil {
			t.Fatalf("read form file: %v", err)
		}
		w.Header().Set("Content-Type", "application/json")
		if err := json.NewEncoder(w).Encode(Episode{
			ID:          "episode-1",
			PodcastID:   "podcast-1",
			Title:       "Episode",
			AudioURL:    "http://example.com/episode.wav",
			DurationSec: 4,
		}); err != nil {
			t.Fatalf("write response: %v", err)
		}
	}))
	defer server.Close()

	client := NewClient(&config.Config{RSSURL: server.URL, HTTPTimeout: 5})
	episode, err := client.publishEpisode(context.Background(), "podcast-1", "Episode", "Script body", audioResponse{
		AudioPath:   audioPath,
		AudioFormat: "wav",
	})
	if err != nil {
		t.Fatalf("publish episode: %v", err)
	}
	if episode.DurationSec != 4 {
		t.Fatalf("got response duration %d, want 4", episode.DurationSec)
	}
	if gotDuration != "4" {
		t.Fatalf("duration_sec field got %q, want 4", gotDuration)
	}
	if gotTitle != "Episode" {
		t.Fatalf("title field got %q, want Episode", gotTitle)
	}
	if gotDescription != "Script body" {
		t.Fatalf("description field got %q, want Script body", gotDescription)
	}
	if gotFilename != filepath.Base(audioPath) {
		t.Fatalf("audio filename got %q, want %q", gotFilename, filepath.Base(audioPath))
	}
}

func writeTestWAV(t *testing.T, seconds int) string {
	t.Helper()
	const sampleRate = 8000
	const channels = 1
	const bitsPerSample = 16
	byteRate := uint32(sampleRate * channels * bitsPerSample / 8)
	blockAlign := uint16(channels * bitsPerSample / 8)
	dataSize := byteRate * uint32(seconds)

	var buf bytes.Buffer
	buf.WriteString("RIFF")
	writeLE(t, &buf, uint32(36)+dataSize)
	buf.WriteString("WAVE")
	buf.WriteString("fmt ")
	writeLE(t, &buf, uint32(16))
	writeLE(t, &buf, uint16(1))
	writeLE(t, &buf, uint16(channels))
	writeLE(t, &buf, uint32(sampleRate))
	writeLE(t, &buf, byteRate)
	writeLE(t, &buf, blockAlign)
	writeLE(t, &buf, uint16(bitsPerSample))
	buf.WriteString("data")
	writeLE(t, &buf, dataSize)
	buf.Write(make([]byte, dataSize))

	path := filepath.Join(t.TempDir(), "episode.wav")
	if err := os.WriteFile(path, buf.Bytes(), 0o644); err != nil {
		t.Fatalf("write wav: %v", err)
	}
	return path
}

func writeLE[T uint16 | uint32](t *testing.T, buf *bytes.Buffer, value T) {
	t.Helper()
	if err := binary.Write(buf, binary.LittleEndian, value); err != nil {
		t.Fatalf("write wav header: %v", err)
	}
}
