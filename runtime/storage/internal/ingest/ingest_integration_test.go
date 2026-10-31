//go:build integration

// Real-MongoDB integration tests for the ingestion path. Run only with `-tags integration`
// against a MongoDB reachable via MONGO_URI (skipped otherwise). They exercise the
// at-least-once + idempotent-storage guarantee against the real archive, including the
// crash window between an archive commit and the progress checkpoint, and the same-identity
// conflict rule. Deterministic faults are injected via the writeWatermark package var.
package ingest

import (
	"context"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"testing"
	"time"

	"aifactory.local/storage/internal/archive"
	"aifactory.local/storage/internal/config"
	"aifactory.local/storage/internal/wal"
)

func realMongo(t *testing.T) (*archive.MongoStore, string) {
	t.Helper()
	uri := os.Getenv("MONGO_URI")
	if uri == "" {
		t.Skip("MONGO_URI not set; skipping real-MongoDB ingest integration test")
	}
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	db := fmt.Sprintf("ing_itest_%d", time.Now().UnixNano())
	s, err := archive.OpenMongo(ctx, uri, db, "archive")
	if err != nil {
		t.Fatalf("OpenMongo: %v", err)
	}
	t.Cleanup(func() { _ = s.Close() })
	return s, db
}

func TestIntegrationAcceptDrainQueryRealMongo(t *testing.T) {
	store, _ := realMongo(t)
	dir := filepath.Join(t.TempDir(), "wal")
	ing, err := Open(dir, config.NewAccountant(config.Default()), store)
	if err != nil {
		t.Fatal(err)
	}
	defer ing.Close()
	if _, err := ing.Accept("k1", msg("p", "s", "m1", "hello mongo"), bigUsage()); err != nil {
		t.Fatal(err)
	}
	if n, err := ing.Drain(); n != 1 || err != nil {
		t.Fatalf("drain: n=%d err=%v", n, err)
	}
	hits, err := ing.Query("p", "mongo", "")
	if err != nil || len(hits) != 1 || hits[0].Text != "hello mongo" {
		t.Fatalf("query: hits=%v err=%v", hits, err)
	}
}

// Crash after the real archive commit but before the checkpoint fsync: on restart the
// record is re-committed, and Mongo's identity idempotency keeps exactly one document.
func TestIntegrationCrashAfterCommitRealMongo(t *testing.T) {
	store, _ := realMongo(t)
	dir := filepath.Join(t.TempDir(), "wal")
	ing, err := Open(dir, config.NewAccountant(config.Default()), store)
	if err != nil {
		t.Fatal(err)
	}
	if _, err := ing.Accept("k1", msg("p", "s", "m1", "v"), bigUsage()); err != nil {
		t.Fatal(err)
	}
	orig := writeWatermark
	writeWatermark = func(string, uint64) error { return fmt.Errorf("injected crash before checkpoint") }
	n, derr := ing.Drain()
	writeWatermark = orig
	if n != 0 || derr == nil {
		t.Fatalf("expected checkpoint failure after commit, got n=%d err=%v", n, derr)
	}
	ing.Close()
	// The document is already durable in Mongo; restart re-commits idempotently.
	ing2, err := Open(dir, config.NewAccountant(config.Default()), store)
	if err != nil {
		t.Fatal(err)
	}
	defer ing2.Close()
	if _, err := ing2.Drain(); err != nil {
		t.Fatalf("re-drain: %v", err)
	}
	if got := mustFetch(t, store, "p"); len(got) != 1 {
		t.Fatalf("exactly one document after crash+restart (no loss, no duplicate), got %d", len(got))
	}
}

// Same identity, different payload, against real Mongo: Drain surfaces ErrIDConflict and
// the first document is not overwritten.
func TestIntegrationSameIDConflictRealMongo(t *testing.T) {
	store, _ := realMongo(t)
	dir := filepath.Join(t.TempDir(), "wal")
	ing, err := Open(dir, config.NewAccountant(config.Default()), store)
	if err != nil {
		t.Fatal(err)
	}
	defer ing.Close()
	if _, err := ing.Accept("k1", msg("p", "s", "m1", "foo"), bigUsage()); err != nil {
		t.Fatal(err)
	}
	// Same identity, different payload, distinct WAL key: now rejected PRE-ADMISSION by the
	// canonical-identity index (V2-3), so it never reaches a durable WAL frame. (The real-Mongo
	// Put ErrIDConflict remains as defense in depth and is exercised in the archive suite.)
	if _, err := ing.Accept("k2", msg("p", "s", "m1", "bar"), bigUsage()); !errors.Is(err, wal.ErrKeyConflict) {
		t.Fatalf("different payload under same identity must conflict pre-admission, got %v", err)
	}
	if _, err := ing.Drain(); err != nil {
		t.Fatalf("drain of the first record must succeed: %v", err)
	}
	got := mustFetch(t, store, "p")
	if len(got) != 1 || got[0].Text != "foo" {
		t.Fatalf("conflict must not overwrite; expected one 'foo', got %v", got)
	}
}

func mustFetch(t *testing.T, s archive.Store, project string) []archive.Record {
	t.Helper()
	r, err := s.Fetch(project)
	if err != nil {
		t.Fatalf("Fetch(%q): %v", project, err)
	}
	return r
}
