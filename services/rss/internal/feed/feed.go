// Package feed renders a podcast and its episodes into iTunes-flavored RSS 2.0 XML.
package feed

import (
	"encoding/xml"
	"fmt"
	"time"

	"github.com/piratepod/rss/internal/db"
)

const (
	itunesNS = "http://www.itunes.com/dtds/podcast-1.0.dtd"
	atomNS   = "http://www.w3.org/2005/Atom"
	rssVer   = "2.0"
)

type rss struct {
	XMLName xml.Name `xml:"rss"`
	Version string   `xml:"version,attr"`
	Itunes  string   `xml:"xmlns:itunes,attr"`
	Atom    string   `xml:"xmlns:atom,attr"`
	Channel channel  `xml:"channel"`
}

type channel struct {
	AtomLink    atomLink       `xml:"atom:link"`
	Title       string         `xml:"title"`
	Link        string         `xml:"link"`
	Language    string         `xml:"language"`
	Description string         `xml:"description"`
	Author      string         `xml:"itunes:author,omitempty"`
	Summary     string         `xml:"itunes:summary,omitempty"`
	Category    itunesCategory `xml:"itunes:category"`
	Explicit    string         `xml:"itunes:explicit"`
	Image       *itunesImage   `xml:"itunes:image,omitempty"`
	Items       []item         `xml:"item"`
}

type atomLink struct {
	Href string `xml:"href,attr"`
	Rel  string `xml:"rel,attr"`
	Type string `xml:"type,attr"`
}

type itunesImage struct {
	Href string `xml:"href,attr"`
}

type itunesCategory struct {
	Text string `xml:"text,attr"`
}

type item struct {
	Title       string    `xml:"title"`
	Description string    `xml:"description,omitempty"`
	Enclosure   enclosure `xml:"enclosure"`
	GUID        guid      `xml:"guid"`
	PubDate     string    `xml:"pubDate"`
	Duration    string    `xml:"itunes:duration,omitempty"`
}

type enclosure struct {
	URL    string `xml:"url,attr"`
	Length int64  `xml:"length,attr"`
	Type   string `xml:"type,attr"`
}

type guid struct {
	IsPermaLink string `xml:"isPermaLink,attr"`
	Value       string `xml:",chardata"`
}

// Render returns the RSS XML for p and its episodes. feedURL is the canonical
// /feeds/{slug} URL used in the atom:link self ref.
func Render(p db.Podcast, eps []db.Episode, feedURL string) ([]byte, error) {
	ch := channel{
		AtomLink: atomLink{
			Href: feedURL,
			Rel:  "self",
			Type: "application/rss+xml",
		},
		Title:       p.Title,
		Link:        feedURL,
		Language:    p.Language,
		Description: p.Description,
		Author:      p.Author,
		Summary:     p.Description,
		Category:    itunesCategory{Text: "Technology"},
		Explicit:    "false",
		Items:       make([]item, 0, len(eps)),
	}
	if p.CoverURL != "" {
		ch.Image = &itunesImage{Href: p.CoverURL}
	}
	for _, ep := range eps {
		ch.Items = append(ch.Items, item{
			Title:       ep.Title,
			Description: ep.Description,
			Enclosure: enclosure{
				URL:    ep.AudioURL,
				Length: ep.AudioBytes,
				Type:   audioType(ep.AudioType),
			},
			GUID:     guid{IsPermaLink: "false", Value: ep.GUID},
			PubDate:  ep.PublishedAt.UTC().Format(time.RFC1123Z),
			Duration: formatDuration(ep.DurationSec),
		})
	}
	doc := rss{
		Version: rssVer,
		Itunes:  itunesNS,
		Atom:    atomNS,
		Channel: ch,
	}
	body, err := xml.MarshalIndent(doc, "", "  ")
	if err != nil {
		return nil, fmt.Errorf("feed: marshal: %w", err)
	}
	return append([]byte(xml.Header), body...), nil
}

func audioType(t string) string {
	if t == "" {
		return "audio/mpeg"
	}
	return t
}

func formatDuration(sec int) string {
	if sec <= 0 {
		return ""
	}
	h := sec / 3600
	m := (sec % 3600) / 60
	s := sec % 60
	if h > 0 {
		return fmt.Sprintf("%d:%02d:%02d", h, m, s)
	}
	return fmt.Sprintf("%d:%02d", m, s)
}
