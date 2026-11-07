//go:build integration

package search

import (
	"aifactory.local/storage/internal/archive"
	"context"
	"fmt"
	"os"
	"testing"
	"time"
)

func realStore(t *testing.T) *Store {
	t.Helper()
	dsn := os.Getenv("PG_DSN")
	if dsn == "" {
		t.Skip("PG_DSN unavailable")
	}
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	s, e := Open(ctx, dsn)
	if e != nil {
		t.Fatal(e)
	}
	t.Cleanup(s.Close)
	return s
}
func TestRealIndexSourceHashRebuildAndBoundedPagination(t *testing.T) {
	s := realStore(t)
	project := fmt.Sprintf("search_%d", time.Now().UnixNano())
	defer s.Purge(project)
	r := archive.Record{Project: project, SourceInstance: "synthetic", SessionID: "s", MessageID: "m", Text: "English \u0399\u0308\u0396\u0391 CAF\u00c9", ConsentEpoch: 1}
	if e := s.Put(r); e != nil {
		t.Fatal(e)
	}
	if ok, e := s.Matches(r); e != nil || !ok {
		t.Fatal(ok, e)
	}
	refs, _, e := s.Window(project, "\u03ca\u03b6\u03b1 cafe\u0301", "")
	if e != nil || len(refs) != 1 {
		t.Fatal(refs, e)
	}
	refs, _, e = s.Window(project, "Eng", "")
	if e != nil || len(refs) != 0 {
		t.Fatal("tokenized search acted as substring", refs, e)
	}
	changed := r
	changed.Text = "different"
	if ok, e := s.Matches(changed); e != nil || ok {
		t.Fatal("stale source hash certified", ok, e)
	}
	if e = s.Purge(project); e != nil {
		t.Fatal(e)
	}
	if ok, e := s.Matches(r); e != nil || ok {
		t.Fatal(ok, e)
	}
	if e = s.Put(r); e != nil {
		t.Fatal(e)
	}
	refs, _, e = s.Window(project, "\u03ca\u03b6\u03b1 cafe\u0301", "")
	if e != nil || len(refs) != 1 || refs[0].PayloadHash != RecordHash(r) {
		t.Fatal("rebuild differs", refs, e)
	}
	for n := 0; n < MaxWindow+7; n++ {
		v := r
		v.MessageID = fmt.Sprint(n)
		if e = s.Put(v); e != nil {
			t.Fatal(e)
		}
	}
	seen := map[string]bool{}
	after := ""
	for pages := 0; pages < 5; pages++ {
		rows, next, e := s.Window(project, "", after)
		if e != nil {
			t.Fatal(e)
		}
		if len(rows) > MaxWindow {
			t.Fatal("unbounded")
		}
		for _, ref := range rows {
			if seen[ref.Identity] {
				t.Fatal("duplicate pagination")
			}
			seen[ref.Identity] = true
		}
		if next == "" {
			break
		}
		after = next
	}
	if len(seen) != MaxWindow+8 {
		t.Fatal("missing page", len(seen))
	}
	rows, _, e := s.Window(project+"-foreign", "", "")
	if e != nil || len(rows) != 0 {
		t.Fatal("cross-project", rows, e)
	}
}
func TestRealIndexRefusesUnknownSchema(t *testing.T) {
	s := realStore(t)
	_, e := s.pool.Exec(context.Background(), `UPDATE derived_index_version SET version=999 WHERE singleton=true`)
	if e != nil {
		t.Fatal(e)
	}
	defer s.pool.Exec(context.Background(), `UPDATE derived_index_version SET version=1 WHERE singleton=true`)
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	other, e := Open(ctx, os.Getenv("PG_DSN"))
	if e == nil {
		other.Close()
		t.Fatal("unknown schema accepted")
	}
}

func TestRealIndexMissingVersionWitnessRefuses(t *testing.T) {
	s := realStore(t)
	_, e := s.pool.Exec(context.Background(), `DELETE FROM derived_index_version`)
	if e != nil {
		t.Fatal(e)
	}
	defer s.pool.Exec(context.Background(), `INSERT INTO derived_index_version VALUES(true,1)`)
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	other, e := Open(ctx, os.Getenv("PG_DSN"))
	if e == nil {
		other.Close()
		t.Fatal("missing witness silently repaired")
	}
}
