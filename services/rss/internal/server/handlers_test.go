package server

import "testing"

func TestAudioUploadTypeAcceptsWAVAndMP3(t *testing.T) {
	tests := []struct {
		name        string
		filename    string
		contentType string
		wantType    string
		wantExt     string
	}{
		{
			name:        "wav extension",
			filename:    "episode.wav",
			contentType: "application/octet-stream",
			wantType:    "audio/wav",
			wantExt:     ".wav",
		},
		{
			name:        "wav content type",
			filename:    "episode",
			contentType: "audio/x-wav",
			wantType:    "audio/wav",
			wantExt:     ".wav",
		},
		{
			name:        "mp3 extension",
			filename:    "episode.mp3",
			contentType: "application/octet-stream",
			wantType:    "audio/mpeg",
			wantExt:     ".mp3",
		},
		{
			name:        "mp3 content type",
			filename:    "episode",
			contentType: "audio/mpeg",
			wantType:    "audio/mpeg",
			wantExt:     ".mp3",
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			gotType, gotExt, err := audioUploadType(tt.filename, tt.contentType)
			if err != nil {
				t.Fatalf("audioUploadType: %v", err)
			}
			if gotType != tt.wantType || gotExt != tt.wantExt {
				t.Fatalf("got %q/%q, want %q/%q", gotType, gotExt, tt.wantType, tt.wantExt)
			}
		})
	}
}

func TestAudioUploadTypeRejectsUnsupportedTypes(t *testing.T) {
	if _, _, err := audioUploadType("episode.txt", "text/plain"); err == nil {
		t.Fatal("expected unsupported type error")
	}
}

func TestRewriteLocalMediaURLUsesConfiguredMediaURL(t *testing.T) {
	got := rewriteLocalMediaURL(
		"http://localhost:8080/media/feed/episode.wav",
		"https://public.example.com/media",
	)

	if want := "https://public.example.com/media/feed/episode.wav"; got != want {
		t.Fatalf("rewriteLocalMediaURL = %q, want %q", got, want)
	}
}

func TestRewriteLocalMediaURLPreservesExternalURL(t *testing.T) {
	got := rewriteLocalMediaURL(
		"https://cdn.example.com/media/feed/episode.wav",
		"https://public.example.com/media",
	)

	if want := "https://cdn.example.com/media/feed/episode.wav"; got != want {
		t.Fatalf("rewriteLocalMediaURL = %q, want %q", got, want)
	}
}
