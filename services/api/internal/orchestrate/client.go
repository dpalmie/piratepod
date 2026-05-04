// Package orchestrate proxies the web API contract to the orchestrate worker.
package orchestrate

import (
	"bytes"
	"context"
	"fmt"
	"io"
	"net/http"
	"strings"
	"time"

	"github.com/piratepod/api/internal/config"
)

type Client struct {
	base string
	http *http.Client
}

func NewClient(cfg *config.Config) *Client {
	return &Client{
		base: strings.TrimRight(cfg.OrchestrateURL, "/"),
		http: &http.Client{Timeout: time.Duration(cfg.HTTPTimeout) * time.Second},
	}
}

func (c *Client) Do(ctx context.Context, method, path string, body io.Reader, contentType string) (*http.Response, error) {
	req, err := http.NewRequestWithContext(ctx, method, c.base+path, body)
	if err != nil {
		return nil, err
	}
	if contentType != "" {
		req.Header.Set("Content-Type", contentType)
	}
	resp, err := c.http.Do(req)
	if err != nil {
		return nil, fmt.Errorf("orchestrate unreachable: %w", err)
	}
	return resp, nil
}

func (c *Client) DoBytes(ctx context.Context, method, path string, body []byte, contentType string) (*http.Response, error) {
	var reader io.Reader
	if body != nil {
		reader = bytes.NewReader(body)
	}
	return c.Do(ctx, method, path, reader, contentType)
}
