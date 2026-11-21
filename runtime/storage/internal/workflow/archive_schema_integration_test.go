//go:build integration

package workflow

import (
	"aifactory.local/storage/internal/config"
	"aifactory.local/storage/internal/control"
	"bufio"
	"context"
	"fmt"
	"github.com/jackc/pgx/v5"
	"net/url"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

func isolatedArchiveSchema(t *testing.T) (*PGStore, string) {
	t.Helper()
	dsn := os.Getenv("PG_DSN")
	if dsn == "" {
		t.Skip("PG_DSN unavailable: real migration NOT_TESTED")
	}
	ctx := context.Background()
	admin, err := pgx.Connect(ctx, dsn)
	if err != nil {
		t.Fatal(err)
	}
	schema := fmt.Sprintf("archive_schema_%d", time.Now().UnixNano())
	if _, err := admin.Exec(ctx, "CREATE SCHEMA "+pgx.Identifier{schema}.Sanitize()); err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() {
		_, _ = admin.Exec(ctx, "DROP SCHEMA "+pgx.Identifier{schema}.Sanitize()+" CASCADE")
		_ = admin.Close(ctx)
	})
	u, err := url.Parse(dsn)
	if err != nil || u.Scheme == "" {
		t.Fatal("fixture requires PostgreSQL URL", err)
	}
	q := u.Query()
	q.Set("search_path", schema)
	u.RawQuery = q.Encode()
	s, err := OpenPostgres(ctx, u.String())
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(s.Close)
	return s, u.String()
}
func TestArchiveSchemaUpgradeIsExplicitIdempotentAndPreservesRows(t *testing.T) {
	s, dsn := isolatedArchiveSchema(t)
	ctx := context.Background()
	var version int
	if err := s.pool.QueryRow(ctx, `SELECT version FROM derived_index_version`).Scan(&version); err != nil || version != 1 {
		t.Fatal("ordinary startup changed metadata schema", version, err)
	}
	if err := s.CAS("p", Task{ID: "task", Version: 1, Fields: map[string]string{"title": "unchanged"}}, 0); err != nil {
		t.Fatal(err)
	}
	if _, err := s.pool.Exec(ctx, `INSERT INTO archive_index VALUES('key','projecthash','p','identity','originalhash',to_tsvector('simple','original content'))`); err != nil {
		t.Fatal(err)
	}
	if err := s.UpgradeArchiveMetadata(ctx); err != nil {
		t.Fatal(err)
	}
	if err := s.UpgradeArchiveMetadata(ctx); err != nil {
		t.Fatal("retry", err)
	}
	if err := s.pool.QueryRow(ctx, `SELECT version FROM derived_index_version`).Scan(&version); err != nil || version != 2 {
		t.Fatal(version, err)
	}
	reopened, err := OpenPostgres(ctx, dsn)
	if err != nil {
		t.Fatal(err)
	}
	defer reopened.Close()
	task, found, err := reopened.Get("p", "task")
	if err != nil || !found || task.Fields["title"] != "unchanged" || task.Version != 1 {
		t.Fatal(task, found, err)
	}
	var identity, payload string
	var metadata *string
	if err := reopened.pool.QueryRow(ctx, `SELECT identity,payload_hash,metadata_hash FROM archive_index WHERE key_hash='key'`).Scan(&identity, &payload, &metadata); err != nil || identity != "identity" || payload != "originalhash" || metadata != nil {
		t.Fatal("legacy row changed", identity, payload, metadata, err)
	}
	if err := reopened.RollbackInitial(ctx, func(map[string][]Task) error { return nil }); err == nil {
		t.Fatal("unreviewed downgrade allowed")
	}
}

func TestArchiveSchemaFailedUpgradeRollsBackAllDDL(t *testing.T) {
	s, _ := isolatedArchiveSchema(t)
	ctx := context.Background()
	// A deliberately conflicting fixture relation fails the LAST CREATE after
	// ALTER/CREATE INDEX ran; transactional rollback must restore the old schema.
	if _, err := s.pool.Exec(ctx, `CREATE TABLE archive_checkpoint(fixture text)`); err != nil {
		t.Fatal(err)
	}
	if err := s.UpgradeArchiveMetadata(ctx); err == nil {
		t.Fatal("conflicting migration succeeded")
	}
	var version int
	if err := s.pool.QueryRow(ctx, `SELECT version FROM derived_index_version`).Scan(&version); err != nil || version != 1 {
		t.Fatal(version, err)
	}
	var upgraded bool
	if err := s.pool.QueryRow(ctx, `SELECT EXISTS(SELECT 1 FROM schema_migrations WHERE name=$1)`, ArchiveMetadataMigration).Scan(&upgraded); err != nil || upgraded {
		t.Fatal("failed upgrade recorded", upgraded, err)
	}
	if _, err := s.pool.Exec(ctx, `SELECT metadata_hash FROM archive_index`); err == nil {
		t.Fatal("partial ALTER survived rollback")
	}
	if _, err := s.pool.Exec(ctx, `DROP TABLE archive_checkpoint`); err != nil {
		t.Fatal(err)
	}
	if err := s.UpgradeArchiveMetadata(ctx); err != nil {
		t.Fatal("retry after rollback", err)
	}
	if _, err := s.pool.Exec(ctx, `INSERT INTO archive_index(key_hash,project_hash,project,identity,payload_hash,terms,metadata_hash,source_generation) VALUES('invalid','p','p','id','hash','',repeat('a',64),'g')`); err == nil {
		t.Fatal("metadata without ordinal accepted")
	}
}

func TestOldServerRefusesOptInPGMetadataSchema(t *testing.T) {
	old := os.Getenv("ARCHIVE_OLD_SERVER")
	if old == "" {
		t.Skip("ARCHIVE_OLD_SERVER unavailable: actual old-server schema refusal NOT_TESTED")
	}
	s, dsn := isolatedArchiveSchema(t)
	root := t.TempDir()
	token := filepath.Join(root, "operator.json")
	if err := os.WriteFile(token, []byte(`{"id":"op","secret":"synthetic-only"}`), 0600); err != nil {
		t.Fatal(err)
	}
	state := filepath.Join(root, "state")
	ctl, err := control.InitializeBudgeted(state, config.Default())
	if err != nil {
		t.Fatal(err)
	}
	if err := ctl.Close(); err != nil {
		t.Fatal(err)
	}
	args := []string{"-state", state, "-operator-token", token, "-listen", "127.0.0.1:0"}
	env := append(os.Environ(), "STORAGE_POSTGRES_ENABLED=1", "STORAGE_POSTGRES_DSN="+dsn)
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	cmd := exec.CommandContext(ctx, old, args...)
	cmd.Env = env
	stdout, err := cmd.StdoutPipe()
	if err != nil {
		t.Fatal(err)
	}
	if err := cmd.Start(); err != nil {
		t.Fatal(err)
	}
	scanner := bufio.NewScanner(stdout)
	ready := scanner.Scan() && strings.HasPrefix(scanner.Text(), "LISTEN ")
	cancel()
	_ = cmd.Wait()
	if !ready {
		t.Fatal("actual old server failed positive baseline002 startup")
	}
	if err := s.UpgradeArchiveMetadata(context.Background()); err != nil {
		t.Fatal(err)
	}
	ctx, cancel = context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	cmd = exec.CommandContext(ctx, old, args...)
	cmd.Env = env
	out, err := cmd.CombinedOutput()
	if err == nil || ctx.Err() != nil || !strings.Contains(string(out), "newer than this image") || strings.Contains(string(out), "LISTEN ") {
		t.Fatalf("old server did not refuse upgraded PG before serving: %s (%v)", out, err)
	}
}

func TestArchiveMetadataSchemaReadinessIsReadOnly(t *testing.T) {
	s, _ := isolatedArchiveSchema(t)
	ctx := context.Background()
	if ready, err := s.ArchiveMetadataReady(ctx); err != nil || ready {
		t.Fatal(ready, err)
	}
	if err := s.UpgradeArchiveMetadata(ctx); err != nil {
		t.Fatal(err)
	}
	if ready, err := s.ArchiveMetadataReady(ctx); err != nil || !ready {
		t.Fatal(ready, err)
	}
}
