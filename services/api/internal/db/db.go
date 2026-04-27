// Package db owns the SQLite handle, migrations, and job repository.
package db

import (
	"database/sql"
	"embed"
	"fmt"
	"os"
	"path/filepath"

	"github.com/pressly/goose/v3"

	_ "modernc.org/sqlite"
)

//go:embed migrations/sqlite/*.sql
var sqliteMigrationsFS embed.FS

func OpenSQLite(path string) (*sql.DB, error) {
	if dir := filepath.Dir(path); dir != "" && dir != "." {
		if err := os.MkdirAll(dir, 0o755); err != nil {
			return nil, fmt.Errorf("db: mkdir %q: %w", dir, err)
		}
	}
	dsn := path + "?_pragma=journal_mode(WAL)&_pragma=foreign_keys(ON)"
	db, err := sql.Open("sqlite", dsn)
	if err != nil {
		return nil, fmt.Errorf("db: open: %w", err)
	}
	if err := db.Ping(); err != nil {
		_ = db.Close()
		return nil, fmt.Errorf("db: ping: %w", err)
	}
	if err := migrateSQLite(db); err != nil {
		_ = db.Close()
		return nil, err
	}
	return db, nil
}

func migrateSQLite(db *sql.DB) error {
	goose.SetBaseFS(sqliteMigrationsFS)
	if err := goose.SetDialect("sqlite3"); err != nil {
		return fmt.Errorf("db: set dialect: %w", err)
	}
	if err := goose.Up(db, "migrations/sqlite"); err != nil {
		return fmt.Errorf("db: migrate: %w", err)
	}
	return nil
}
