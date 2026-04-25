package db

import (
	"context"
	"database/sql"
	"errors"
	"fmt"
	"time"
)

var ErrNotFound = errors.New("db: not found")

type Podcast struct {
	ID          string
	OwnerID     string
	Slug        string
	Title       string
	Description string
	Author      string
	CoverURL    string
	Language    string
	CreatedAt   time.Time
}

type Episode struct {
	ID          string
	PodcastID   string
	Title       string
	Description string
	AudioURL    string
	AudioType   string
	AudioBytes  int64
	DurationSec int
	GUID        string
	PublishedAt time.Time
}

type Repo struct{ db *sql.DB }

func NewRepo(db *sql.DB) *Repo { return &Repo{db: db} }

func (r *Repo) CreatePodcast(ctx context.Context, p Podcast) (Podcast, error) {
	if p.CreatedAt.IsZero() {
		p.CreatedAt = time.Now().UTC()
	}
	if p.Language == "" {
		p.Language = "en"
	}
	_, err := r.db.ExecContext(ctx, `
        INSERT INTO podcasts (id, owner_id, slug, title, description, author, cover_url, language, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)`,
		p.ID, p.OwnerID, p.Slug, p.Title, nullable(p.Description),
		nullable(p.Author), nullable(p.CoverURL), p.Language, p.CreatedAt.Format(time.RFC3339Nano),
	)
	if err != nil {
		return Podcast{}, fmt.Errorf("db: create podcast: %w", err)
	}
	return p, nil
}

func (r *Repo) GetPodcastBySlug(ctx context.Context, slug string) (Podcast, error) {
	row := r.db.QueryRowContext(ctx, `
        SELECT id, owner_id, slug, title, description, author, cover_url, language, created_at
        FROM podcasts WHERE slug = ?`, slug)
	return scanPodcast(row)
}

func (r *Repo) GetPodcastByID(ctx context.Context, id string) (Podcast, error) {
	row := r.db.QueryRowContext(ctx, `
        SELECT id, owner_id, slug, title, description, author, cover_url, language, created_at
        FROM podcasts WHERE id = ?`, id)
	return scanPodcast(row)
}

func (r *Repo) ListPodcastsByOwner(ctx context.Context, ownerID string) ([]Podcast, error) {
	rows, err := r.db.QueryContext(ctx, `
        SELECT id, owner_id, slug, title, description, author, cover_url, language, created_at
        FROM podcasts WHERE owner_id = ? ORDER BY created_at DESC`, ownerID)
	if err != nil {
		return nil, fmt.Errorf("db: list podcasts: %w", err)
	}
	defer rows.Close()
	var out []Podcast
	for rows.Next() {
		p, err := scanPodcastRows(rows)
		if err != nil {
			return nil, err
		}
		out = append(out, p)
	}
	return out, rows.Err()
}

func (r *Repo) DeletePodcast(ctx context.Context, id, ownerID string) error {
	res, err := r.db.ExecContext(ctx, `DELETE FROM podcasts WHERE id = ? AND owner_id = ?`, id, ownerID)
	if err != nil {
		return fmt.Errorf("db: delete podcast: %w", err)
	}
	n, _ := res.RowsAffected()
	if n == 0 {
		return ErrNotFound
	}
	return nil
}

func (r *Repo) CreateEpisode(ctx context.Context, e Episode) (Episode, error) {
	if e.PublishedAt.IsZero() {
		e.PublishedAt = time.Now().UTC()
	}
	if e.AudioType == "" {
		e.AudioType = "audio/mpeg"
	}
	_, err := r.db.ExecContext(ctx, `
        INSERT INTO episodes (id, podcast_id, title, description, audio_url, audio_type, audio_bytes, duration_sec, guid, published_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
		e.ID, e.PodcastID, e.Title, nullable(e.Description), e.AudioURL, e.AudioType,
		e.AudioBytes, nullableInt(e.DurationSec), e.GUID, e.PublishedAt.Format(time.RFC3339Nano),
	)
	if err != nil {
		return Episode{}, fmt.Errorf("db: create episode: %w", err)
	}
	return e, nil
}

func (r *Repo) ListEpisodesByPodcastID(ctx context.Context, podcastID string) ([]Episode, error) {
	rows, err := r.db.QueryContext(ctx, `
        SELECT id, podcast_id, title, description, audio_url, audio_type, audio_bytes, duration_sec, guid, published_at
        FROM episodes WHERE podcast_id = ? ORDER BY published_at DESC`, podcastID)
	if err != nil {
		return nil, fmt.Errorf("db: list episodes: %w", err)
	}
	defer rows.Close()
	var out []Episode
	for rows.Next() {
		e, err := scanEpisodeRows(rows)
		if err != nil {
			return nil, err
		}
		out = append(out, e)
	}
	return out, rows.Err()
}

func scanPodcast(row *sql.Row) (Podcast, error) {
	var p Podcast
	var desc, author, cover sql.NullString
	var createdAt string
	err := row.Scan(&p.ID, &p.OwnerID, &p.Slug, &p.Title, &desc, &author, &cover, &p.Language, &createdAt)
	if errors.Is(err, sql.ErrNoRows) {
		return Podcast{}, ErrNotFound
	}
	if err != nil {
		return Podcast{}, fmt.Errorf("db: scan podcast: %w", err)
	}
	p.Description, p.Author, p.CoverURL = desc.String, author.String, cover.String
	p.CreatedAt, err = parseTime(createdAt)
	if err != nil {
		return Podcast{}, err
	}
	return p, nil
}

func scanPodcastRows(rows *sql.Rows) (Podcast, error) {
	var p Podcast
	var desc, author, cover sql.NullString
	var createdAt string
	if err := rows.Scan(&p.ID, &p.OwnerID, &p.Slug, &p.Title, &desc, &author, &cover, &p.Language, &createdAt); err != nil {
		return Podcast{}, fmt.Errorf("db: scan podcast: %w", err)
	}
	p.Description, p.Author, p.CoverURL = desc.String, author.String, cover.String
	t, err := parseTime(createdAt)
	if err != nil {
		return Podcast{}, err
	}
	p.CreatedAt = t
	return p, nil
}

func scanEpisodeRows(rows *sql.Rows) (Episode, error) {
	var e Episode
	var desc sql.NullString
	var duration sql.NullInt64
	var publishedAt string
	if err := rows.Scan(
		&e.ID, &e.PodcastID, &e.Title, &desc, &e.AudioURL, &e.AudioType,
		&e.AudioBytes, &duration, &e.GUID, &publishedAt,
	); err != nil {
		return Episode{}, fmt.Errorf("db: scan episode: %w", err)
	}
	e.Description = desc.String
	if duration.Valid {
		e.DurationSec = int(duration.Int64)
	}
	t, err := parseTime(publishedAt)
	if err != nil {
		return Episode{}, err
	}
	e.PublishedAt = t
	return e, nil
}

func parseTime(s string) (time.Time, error) {
	// Accept both RFC3339Nano and sqlite strftime formats.
	if t, err := time.Parse(time.RFC3339Nano, s); err == nil {
		return t, nil
	}
	if t, err := time.Parse("2006-01-02T15:04:05.000Z", s); err == nil {
		return t, nil
	}
	if t, err := time.Parse("2006-01-02 15:04:05", s); err == nil {
		return t, nil
	}
	return time.Time{}, fmt.Errorf("db: cannot parse time %q", s)
}

func nullable(s string) any {
	if s == "" {
		return nil
	}
	return s
}

func nullableInt(n int) any {
	if n == 0 {
		return nil
	}
	return n
}
