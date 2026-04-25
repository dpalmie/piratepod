// Package storage abstracts podcast media storage.
package storage

import (
	"context"
	"errors"
	"io"
)

// ErrServedExternally signals that bytes are served outside this process
// (e.g. R2 + CDN). Feed XML embeds the direct URL; the service never proxies.
var ErrServedExternally = errors.New("storage: served externally")

type Storage interface {
	Put(ctx context.Context, key string, r io.Reader, contentType string) error
	URLFor(ctx context.Context, key string) string
	Open(ctx context.Context, key string) (io.ReadSeekCloser, error)
}
