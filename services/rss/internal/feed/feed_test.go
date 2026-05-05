package feed

import (
	"encoding/xml"
	"strings"
	"testing"
	"time"

	"github.com/piratepod/rss/internal/db"
)

func TestRenderProducesValidXMLWithIdentifyingElements(t *testing.T) {
	pub := time.Date(2026, 4, 24, 12, 0, 0, 0, time.UTC)
	p := db.Podcast{
		ID:          "podcast-1",
		OwnerID:     "self",
		Slug:        "xK9mBq2n",
		Title:       "Tech Talk",
		Description: "A podcast about tech",
		Author:      "Alice",
		CoverURL:    "https://example.com/cover.jpg",
		Language:    "en",
		CreatedAt:   pub,
	}
	eps := []db.Episode{{
		ID:          "ep-1",
		PodcastID:   p.ID,
		Title:       "Pilot",
		Description: "First episode",
		AudioURL:    "https://example.com/media/xK9mBq2n/ep-1.wav",
		AudioType:   "audio/wav",
		AudioBytes:  12345,
		DurationSec: 3723, // 1h 2m 3s
		GUID:        "ep-1",
		PublishedAt: pub,
	}}

	got, err := Render(p, eps, "https://example.com/feeds/xK9mBq2n")
	if err != nil {
		t.Fatalf("Render: %v", err)
	}

	if err := xml.Unmarshal(got, new(any)); err != nil {
		t.Fatalf("produced XML is not well-formed: %v\n%s", err, got)
	}

	text := string(got)
	wants := []string{
		`<?xml version="1.0" encoding="UTF-8"?>`,
		`version="2.0"`,
		`xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd"`,
		`xmlns:atom="http://www.w3.org/2005/Atom"`,
		`<title>Tech Talk</title>`,
		`<itunes:author>Alice</itunes:author>`,
		`<itunes:category text="Technology"></itunes:category>`,
		`<itunes:explicit>false</itunes:explicit>`,
		`<itunes:image href="https://example.com/cover.jpg"></itunes:image>`,
		`<enclosure url="https://example.com/media/xK9mBq2n/ep-1.wav" length="12345" type="audio/wav"></enclosure>`,
		`<guid isPermaLink="false">ep-1</guid>`,
		`<itunes:duration>1:02:03</itunes:duration>`,
	}
	for _, w := range wants {
		if !strings.Contains(text, w) {
			t.Errorf("output missing %q\n--- got ---\n%s", w, text)
		}
	}
}

func TestFormatDuration(t *testing.T) {
	cases := map[int]string{
		0:     "",
		-1:    "",
		45:    "0:45",
		125:   "2:05",
		3600:  "1:00:00",
		3723:  "1:02:03",
		36000: "10:00:00",
	}
	for sec, want := range cases {
		if got := formatDuration(sec); got != want {
			t.Errorf("formatDuration(%d) = %q, want %q", sec, got, want)
		}
	}
}

func TestRenderOmitsImageWhenNoCover(t *testing.T) {
	p := db.Podcast{ID: "id", Slug: "s", Title: "t", Language: "en"}
	got, err := Render(p, nil, "https://example.com/feeds/s")
	if err != nil {
		t.Fatalf("Render: %v", err)
	}
	if strings.Contains(string(got), "itunes:image") {
		t.Errorf("expected no itunes:image element, got:\n%s", got)
	}
}
