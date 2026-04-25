package storage

import (
	"context"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"strings"
)

// LocalStorage writes media to disk and serves it in-process via
// http.ServeContent, which handles Range requests natively.
type LocalStorage struct {
	baseDir  string
	mediaURL string
}

func NewLocal(baseDir, mediaURL string) (*LocalStorage, error) {
	if baseDir == "" {
		return nil, fmt.Errorf("storage: baseDir is required")
	}
	if err := os.MkdirAll(baseDir, 0o755); err != nil {
		return nil, fmt.Errorf("storage: mkdir %q: %w", baseDir, err)
	}
	return &LocalStorage{
		baseDir:  baseDir,
		mediaURL: strings.TrimRight(mediaURL, "/"),
	}, nil
}

func (s *LocalStorage) Put(ctx context.Context, key string, r io.Reader, _ string) error {
	path, err := s.resolve(key)
	if err != nil {
		return err
	}
	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		return fmt.Errorf("storage: mkdir: %w", err)
	}
	f, err := os.Create(path)
	if err != nil {
		return fmt.Errorf("storage: create: %w", err)
	}
	defer f.Close()
	if _, err := io.Copy(f, r); err != nil {
		_ = os.Remove(path)
		return fmt.Errorf("storage: write: %w", err)
	}
	return nil
}

func (s *LocalStorage) URLFor(_ context.Context, key string) string {
	return s.mediaURL + "/" + strings.TrimLeft(key, "/")
}

func (s *LocalStorage) Open(_ context.Context, key string) (io.ReadSeekCloser, error) {
	path, err := s.resolve(key)
	if err != nil {
		return nil, err
	}
	return os.Open(path)
}

// resolve joins key to the base directory and rejects paths that would escape
// the base dir via traversal.
func (s *LocalStorage) resolve(key string) (string, error) {
	cleaned := filepath.Clean("/" + key)
	path := filepath.Join(s.baseDir, cleaned)
	abs, err := filepath.Abs(path)
	if err != nil {
		return "", fmt.Errorf("storage: abs: %w", err)
	}
	base, err := filepath.Abs(s.baseDir)
	if err != nil {
		return "", fmt.Errorf("storage: abs base: %w", err)
	}
	if !strings.HasPrefix(abs, base+string(os.PathSeparator)) && abs != base {
		return "", fmt.Errorf("storage: path escapes base: %q", key)
	}
	return abs, nil
}
