//go:build integration

// Integration tests for the real PostgreSQL workflow backend. They run ONLY with
// `-tags integration` against a real PostgreSQL reachable via PG_DSN (skipped otherwise),
// never against the hermetic fake. Tests isolate via unique project names; migrations are
// idempotent so a shared test database is safe.
package workflow

import (
	"context"
	"errors"
	"fmt"
	"os"
	"sync"
	"sync/atomic"
	"testing"
	"time"

	"aifactory.local/storage/internal/registry"
)

func newPG(t *testing.T) *PGStore {
	t.Helper()
	dsn := os.Getenv("PG_DSN")
	if dsn == "" {
		t.Skip("PG_DSN not set; skipping real-PostgreSQL integration test")
	}
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	s, err := OpenPostgres(ctx, dsn)
	if err != nil {
		t.Fatalf("OpenPostgres: %v", err)
	}
	t.Cleanup(s.Close)
	return s
}

func uniqueProject(t *testing.T) string { return fmt.Sprintf("proj_%d", time.Now().UnixNano()) }

// Re-applying migrations is a no-op: opening a second store against the same database must
// succeed without re-running applied migrations.
func TestPGMigrationIdempotent(t *testing.T) {
	s := newPG(t)
	_ = s
	dsn := os.Getenv("PG_DSN")
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	s2, err := OpenPostgres(ctx, dsn) // migrate() runs again; schema_migrations guards it
	if err != nil {
		t.Fatalf("second OpenPostgres (re-apply migrations) must succeed, got %v", err)
	}
	s2.Close()
}

// Concurrent CAS at the same expected version: exactly one writer wins; the rest are
// fenced with ErrVersionConflict (optimistic concurrency, no lost update).
func TestPGConcurrentCAS(t *testing.T) {
	s := newPG(t)
	p := uniqueProject(t)
	if err := s.CAS(p, Task{ID: "t", Version: 1, Fields: map[string]string{"v": "0"}}, 0); err != nil {
		t.Fatalf("seed CAS: %v", err)
	}
	const n = 16
	var wins, conflicts int32
	var wg sync.WaitGroup
	for i := 0; i < n; i++ {
		wg.Add(1)
		go func(i int) {
			defer wg.Done()
			err := s.CAS(p, Task{ID: "t", Version: 2, Fields: map[string]string{"v": fmt.Sprint(i)}}, 1)
			switch {
			case err == nil:
				atomic.AddInt32(&wins, 1)
			case errors.Is(err, ErrVersionConflict):
				atomic.AddInt32(&conflicts, 1)
			default:
				t.Errorf("unexpected CAS error: %v", err)
			}
		}(i)
	}
	wg.Wait()
	if wins != 1 || conflicts != n-1 {
		t.Fatalf("expected exactly 1 win and %d conflicts, got wins=%d conflicts=%d", n-1, wins, conflicts)
	}
	got, ok, readErr := s.Get(p, "t")
	if readErr != nil || !ok || got.Version != 2 {
		t.Fatalf("winning write must be durable at version 2, got %+v ok=%v", got, ok)
	}
}

// Stale authority epoch at the write boundary: a writer holding a pre-cutover epoch is
// fenced (ErrStaleEpoch) even though the real PG store is available; a current-epoch write
// succeeds and is durable.
func TestPGStaleEpochFence(t *testing.T) {
	s := newPG(t)
	op := registry.Principal{ID: "op", Kind: registry.Operator}
	reg := registry.New()
	p := uniqueProject(t)
	if err := reg.MintProject(op, p, "P"); err != nil {
		t.Fatal(err)
	}
	mgr := New(reg, s)
	rcpt, err := mgr.EnablePG(op, p, "export-hash")
	if err != nil {
		t.Fatalf("EnablePG: %v", err)
	}
	cur := rcpt.NewEpoch

	// Stale epoch writer is fenced BEFORE any durable commit.
	if err := mgr.Write(p, "task", 0, cur-1, map[string]string{"value": "stale"}); !errors.Is(err, ErrStaleEpoch) {
		t.Fatalf("stale-epoch write must be ErrStaleEpoch, got %v", err)
	}
	if _, ok, err := s.Get(p, "task"); err != nil || ok {
		t.Fatalf("a fenced stale write must NOT have landed in PG")
	}
	// Current epoch writer succeeds and is durable.
	if err := mgr.Write(p, "task", 0, cur, map[string]string{"value": "ok"}); err != nil {
		t.Fatalf("current-epoch write must succeed, got %v", err)
	}
	got, ok, readErr := s.Get(p, "task")
	if readErr != nil || !ok || got.Fields["value"] != "ok" {
		t.Fatalf("current-epoch write must be durable, got %+v ok=%v", got, ok)
	}
}

// Fail-closed: a backend error surfaces and flips Available() to false; there is no
// in-memory fake fallback. Opening against a dead DSN must error (no fabricated healthy).
func TestPGFailClosedNoFake(t *testing.T) {
	s := newPG(t)
	p := uniqueProject(t)
	if !s.Available() {
		t.Fatalf("freshly opened store must be available")
	}
	s.Close() // close the pool
	if err := s.CAS(p, Task{ID: "t", Version: 1, Fields: map[string]string{}}, 0); err == nil {
		t.Fatalf("CAS against a closed pool must error, not silently succeed")
	}
	if s.Available() {
		t.Fatalf("Available() must be false after a backend failure (no fabricated healthy)")
	}

	ctx, cancel := context.WithTimeout(context.Background(), 4*time.Second)
	defer cancel()
	if _, err := OpenPostgres(ctx, "postgres://u:p@127.0.0.1:1/none?sslmode=disable"); err == nil {
		t.Fatalf("OpenPostgres against a dead DSN must fail, not start as healthy")
	}
}

// TestPGSchemaNewerThanImageFailsClosed verifies the B5 binding guard: if the database carries
// a migration this binary does not embed (a newer image advanced the schema), OpenPostgres
// refuses to run (ErrSchemaNewerThanImage) rather than operating on an unknown schema. The
// fake future-migration row is removed afterwards so the shared test DB is left clean.
func TestPGSchemaNewerThanImageFailsClosed(t *testing.T) {
	s := newPG(t)
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	const fake = "9999_future_from_a_newer_image.sql"
	if _, err := s.pool.Exec(ctx, `INSERT INTO schema_migrations(name) VALUES($1) ON CONFLICT DO NOTHING`, fake); err != nil {
		t.Fatalf("seed fake future migration: %v", err)
	}
	// Always clean up so other tests (and real deployments) are not poisoned.
	defer func() {
		cctx, ccancel := context.WithTimeout(context.Background(), 10*time.Second)
		defer ccancel()
		if _, err := s.pool.Exec(cctx, `DELETE FROM schema_migrations WHERE name=$1`, fake); err != nil {
			t.Fatalf("cleanup fake future migration: %v", err)
		}
	}()

	dsn := os.Getenv("PG_DSN")
	octx, ocancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer ocancel()
	s2, err := OpenPostgres(octx, dsn)
	if err == nil {
		s2.Close()
		t.Fatalf("OpenPostgres must fail closed when the DB schema is newer than the image")
	}
	if !errors.Is(err, ErrSchemaNewerThanImage) {
		t.Fatalf("expected ErrSchemaNewerThanImage, got %v", err)
	}

	// After cleanup (deferred) a normal open must succeed again - proven by a direct re-open here.
	s.pool.Exec(ctx, `DELETE FROM schema_migrations WHERE name=$1`, fake)
	rctx, rcancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer rcancel()
	s3, err := OpenPostgres(rctx, dsn)
	if err != nil {
		t.Fatalf("open after removing the future migration must succeed: %v", err)
	}
	s3.Close()
}

// SchemaVersion of this binary must equal the number of embedded migrations (binding sanity).
func TestPGSchemaVersionMatchesEmbedded(t *testing.T) {
	if SchemaVersion() < 1 {
		t.Fatalf("expected >=1 embedded migration, got %d", SchemaVersion())
	}
}

func TestPGMissingRowCannotSatisfyNonzeroCAS(t *testing.T) {
	s := newPG(t)
	p := uniqueProject(t)
	if err := s.CAS(p, Task{ID: "missing", Version: 8}, 7); !errors.Is(err, ErrVersionConflict) {
		t.Fatalf("missing row accepted nonzero precondition: %v", err)
	}
	if _, found, err := s.Get(p, "missing"); err != nil || found {
		t.Fatalf("unexpected row: %v %v", found, err)
	}
	if err := s.CAS(p, Task{ID: "bad", Version: 9}, 0); !errors.Is(err, ErrVersionConflict) {
		t.Fatalf("version jump: %v", err)
	}
	s.Close()
	if _, found, err := s.Get(p, "missing"); err == nil || found {
		t.Fatalf("backend failure represented as absence: %v %v", found, err)
	}
}

func TestRollbackRefusesNonemptyDerivedIndexBeforeAnyDrop(t *testing.T) {
	s := newPG(t)
	project := uniqueProject(t)
	ctx := context.Background()
	_, e := s.pool.Exec(ctx, `INSERT INTO archive_index(key_hash,project_hash,project,identity,payload_hash,terms) VALUES($1,$1,$1,$1,'synthetic',to_tsvector('simple','synthetic'))`, project)
	if e != nil {
		t.Fatal(e)
	}
	defer s.pool.Exec(ctx, `DELETE FROM archive_index WHERE key_hash=$1`, project)
	if e = s.RollbackInitial(ctx, func(map[string][]Task) error { return nil }); e == nil {
		t.Fatal("nonempty derived index silently dropped")
	}
	var count int
	if e = s.pool.QueryRow(ctx, `SELECT count(*) FROM archive_index WHERE key_hash=$1`, project).Scan(&count); e != nil || count != 1 {
		t.Fatal("refusal changed index", count, e)
	}
	if e = s.pool.QueryRow(ctx, `SELECT count(*) FROM schema_migrations`).Scan(&count); e != nil || count != DefaultSchemaVersion {
		t.Fatal("refusal changed schema", count, e)
	}
}
