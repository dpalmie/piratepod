package db

import (
	"context"
	"path/filepath"
	"strings"
	"testing"
)

func TestResetRunningToQueuedFailsPublishStageJobs(t *testing.T) {
	ctx := context.Background()
	handle, err := OpenSQLite(filepath.Join(t.TempDir(), "test.db"))
	if err != nil {
		t.Fatalf("open sqlite: %v", err)
	}
	defer handle.Close()
	repo := NewRepo(handle)

	if _, err := repo.CreateJob(ctx, "publish-job", "owner", "", `{"urls":["https://example.com/a"]}`); err != nil {
		t.Fatalf("create publish job: %v", err)
	}
	if _, err := repo.CreateJob(ctx, "ingest-job", "owner", "", `{"urls":["https://example.com/b"]}`); err != nil {
		t.Fatalf("create ingest job: %v", err)
	}
	if _, err := handle.ExecContext(ctx, `UPDATE jobs SET status = ?, stage = ? WHERE id = ?`, StatusRunning, StagePublish, "publish-job"); err != nil {
		t.Fatalf("mark publish running: %v", err)
	}
	if _, err := handle.ExecContext(ctx, `UPDATE jobs SET status = ?, stage = ? WHERE id = ?`, StatusRunning, StageIngest, "ingest-job"); err != nil {
		t.Fatalf("mark ingest running: %v", err)
	}

	if err := repo.ResetRunningToQueued(ctx); err != nil {
		t.Fatalf("reset running: %v", err)
	}

	publishJob, err := repo.GetJob(ctx, "publish-job", "owner")
	if err != nil {
		t.Fatalf("get publish job: %v", err)
	}
	if publishJob.Status != StatusFailed || publishJob.Stage != StagePublish {
		t.Fatalf("publish job got status/stage %s/%s, want %s/%s", publishJob.Status, publishJob.Stage, StatusFailed, StagePublish)
	}
	if !strings.Contains(publishJob.Error, "retry may duplicate") {
		t.Fatalf("publish job error %q does not explain duplicate risk", publishJob.Error)
	}

	ingestJob, err := repo.GetJob(ctx, "ingest-job", "owner")
	if err != nil {
		t.Fatalf("get ingest job: %v", err)
	}
	if ingestJob.Status != StatusQueued || ingestJob.Stage != StageQueued {
		t.Fatalf("ingest job got status/stage %s/%s, want %s/%s", ingestJob.Status, ingestJob.Stage, StatusQueued, StageQueued)
	}
}
