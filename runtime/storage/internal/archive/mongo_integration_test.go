//go:build integration

// Integration tests for the real MongoDB archive backend. They run ONLY with
// `-tags integration` against a real MongoDB reachable via MONGO_URI (skipped otherwise),
// never against the hermetic fake. Each test uses a throwaway database dropped on cleanup.
package archive

import (
	"context"
	"errors"
	"fmt"
	"os"
	"testing"
	"time"
)

func newMongoStore(t *testing.T) *MongoStore {
	t.Helper()
	uri := os.Getenv("MONGO_URI")
	if uri == "" {
		t.Skip("MONGO_URI not set; skipping real-MongoDB integration test")
	}
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	db := fmt.Sprintf("itest_%d", time.Now().UnixNano())
	s, err := OpenMongo(ctx, uri, db, "archive")
	if err != nil {
		t.Fatalf("OpenMongo: %v", err)
	}
	t.Cleanup(func() {
		dctx, dcancel := context.WithTimeout(context.Background(), 10*time.Second)
		defer dcancel()
		_ = s.client.Database(db).Drop(dctx)
		_ = s.Close()
	})
	return s
}

func rec(project, session, message, text string) Record {
	return Record{Project: project, SessionID: session, MessageID: message, Seq: 1,
		Type: TypeMessage, Role: "user", Text: text}
}

// Composite-ID collision absence: tuples that a delimiter-joined key would collide
// ("a|b","c" vs "a","b|c") must be stored as DISTINCT records.
func TestMongoCompositeIDNoCollision(t *testing.T) {
	s := newMongoStore(t)
	r1 := rec("a|b", "c", "m", "first")
	r2 := rec("a", "b|c", "m", "second")
	if err := s.Put(r1); err != nil {
		t.Fatalf("put r1: %v", err)
	}
	if err := s.Put(r2); err != nil {
		t.Fatalf("put r2: %v", err)
	}
	if got := mustFetch(t, s, "a|b"); len(got) != 1 || got[0].Text != "first" {
		t.Fatalf("project \"a|b\" must hold exactly r1, got %+v", got)
	}
	if got := mustFetch(t, s, "a"); len(got) != 1 || got[0].Text != "second" {
		t.Fatalf("project \"a\" must hold exactly r2, got %+v", got)
	}
}

// Replay with identical content is idempotent; the same identity with a DIFFERENT payload
// is a surfaced conflict (ErrIDConflict), never a silent drop or overwrite.
func TestMongoReplayIdempotentAndConflict(t *testing.T) {
	s := newMongoStore(t)
	r := rec("p", "s", "m", "foo")
	if err := s.Put(r); err != nil {
		t.Fatalf("put: %v", err)
	}
	if err := s.Put(r); err != nil {
		t.Fatalf("identical replay must be idempotent, got %v", err)
	}
	if got := mustFetch(t, s, "p"); len(got) != 1 {
		t.Fatalf("idempotent replay must keep exactly 1 record, got %d", len(got))
	}
	conflict := rec("p", "s", "m", "bar") // same identity, different payload
	if err := s.Put(conflict); !errors.Is(err, ErrIDConflict) {
		t.Fatalf("different payload under same identity must be ErrIDConflict, got %v", err)
	}
	if got := mustFetch(t, s, "p"); len(got) != 1 || got[0].Text != "foo" {
		t.Fatalf("conflicting payload must NOT overwrite; expected foo, got %+v", got)
	}
}

// Fail-closed: a backend error does not fall back to a fake; it surfaces and flips
// Available() to false. Opening against a dead address must error (no fabricated healthy).
func TestMongoFailClosedNoFake(t *testing.T) {
	s := newMongoStore(t)
	if !s.Available() {
		t.Fatalf("freshly opened store must be available")
	}
	_ = s.Close() // sever the connection
	if err := s.Put(rec("p", "s", "m2", "x")); err == nil {
		t.Fatalf("Put against a severed backend must error, not silently succeed")
	}
	if s.Available() {
		t.Fatalf("Available() must be false after a backend failure (no fabricated healthy)")
	}

	ctx, cancel := context.WithTimeout(context.Background(), 4*time.Second)
	defer cancel()
	if _, err := OpenMongo(ctx, "mongodb://127.0.0.1:1/", "x", "y"); err == nil {
		t.Fatalf("OpenMongo against a dead address must fail, not start as healthy")
	}
}

// mustFetch is a test convenience: Fetch and fail on a read error (production uses Fetch's
// error directly; the old swallowing All is gone - R6).
func mustFetch(t *testing.T, s Store, project string) []Record {
	t.Helper()
	r, err := s.Fetch(project)
	if err != nil {
		t.Fatalf("Fetch(%q): %v", project, err)
	}
	return r
}

func TestMongoWindowUnicodeOriginalProvenance(t *testing.T) {
	s := newMongoStore(t)
	original := "English \u0399\u0308\u0396\u0391 Cafe\u0301"
	r := rec("normalization", "s", "m", original)
	r.SourceInstance = "synthetic-source"
	if e := s.Put(r); e != nil {
		t.Fatal(e)
	}
	window, e := s.Scan(r.Project, nil)
	if e != nil {
		t.Fatal(e)
	}
	hits := Query(window.Records, "\u03ca\u03b6\u03b1 caf\u00e9", "")
	if len(hits) != 1 || hits[0].Text != original || hits[0].SourceInstance != r.SourceInstance || hits[0].MessageID != r.MessageID {
		t.Fatalf("normalization lost original/provenance: %+v", hits)
	}
	stored, found, e := s.Lookup(r)
	if e != nil || !found || stored != r {
		t.Fatalf("comparison altered stored bytes: found=%v err=%v", found, e)
	}
}
