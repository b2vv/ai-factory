package ingest

// Codex v4 ingest-level regressions (adopted faithfully from the v4 review, reformatted):
//   - durable-change whose SIZE cannot be re-measured => next admission fails closed, then
//     self-heals once the size is measurable again (V3-2);
//   - the monotonic cross-request reservation counter survives a duplicate no-op and a Compact
//     without decreasing, and canonical identity survives a reopen (V3-3);
//   - concurrent identical-duplicate / new / conflicting accepts charge exactly one new record.
// The direct durable-error reservation (V3-1 Codex v4) is also asserted here: the counter grows
// on the committed-index-persist error path and a retry does not double-charge.

import (
	"os"
	"path/filepath"
	"testing"

	"aifactory.local/storage/internal/archive"
	"aifactory.local/storage/internal/config"
)

func TestCodexV4UnknownAccountingRefuseThenHeal(t *testing.T) {
	d := t.TempDir()
	i, e := Open(d, config.NewAccountant(config.Default()), archive.NewMemStore())
	if e != nil {
		t.Fatal(e)
	}
	defer i.Close()
	r := archive.Record{Project: "p", MessageID: "a"}
	u := config.Usage{FreeBytes: 1 << 40}

	// A committed.idx that is a self-referential symlink: the accept marker is still fsync'd
	// (durable accept), but both the index persist AND the subsequent size re-measurement fail.
	idx := filepath.Join(d, "committed.idx")
	os.Remove(idx)
	os.Symlink("committed.idx", idx)
	rc, e := i.Accept("a", r, u)
	if e == nil || rc.Seq != 1 {
		t.Fatalf("fault not durable %+v %v", rc, e)
	}
	// The durable record's reservation must still be counted even though Accept errored
	// (V3-1 Codex v4): a committed-index failure is a fully durable accept.
	if i.AcceptedBytes() <= 0 {
		t.Fatalf("durable-error accept did not reserve its cost: acceptedTotal=%d", i.AcceptedBytes())
	}

	// Size now unknown => the NEXT admission must fail closed, not trust a stale counter.
	r.MessageID = "b"
	if _, e = i.Accept("b", r, u); e == nil {
		t.Fatal("unknown accounting admitted")
	}
	// Repair the index file and retry: accounting self-heals and the record is accepted.
	os.Remove(idx)
	os.WriteFile(idx, nil, 0600)
	if _, e = i.Accept("b", r, u); e != nil {
		t.Fatalf("selfheal failed %v", e)
	}
	if n, e := i.AcceptedCount(); e != nil || n != 2 {
		t.Fatalf("wrong accepted records %d %v", n, e)
	}
}

func TestCodexV4MonotonicCompactDuplicateReopen(t *testing.T) {
	d := t.TempDir()
	cfg := config.NewAccountant(config.Default())
	i, e := Open(d, cfg, archive.NewMemStore())
	if e != nil {
		t.Fatal(e)
	}
	r := archive.Record{Project: "p", MessageID: "a"}
	u := config.Usage{FreeBytes: 1 << 40}
	i.Accept("legacy", r, u)
	n := i.AcceptedBytes()
	if n <= 0 {
		t.Fatal("counter not incremented")
	}
	rc, e := i.Accept(archive.IdentityKey(r), r, u)
	if e != nil || !rc.Duplicate || i.AcceptedBytes() != n {
		t.Fatalf("duplicate not no-op %+v %v", rc, e)
	}
	if _, e = i.Compact(func(archive.Record) bool { return false }); e != nil {
		t.Fatal(e)
	}
	if i.AcceptedBytes() != n {
		t.Fatal("compaction decreased monotonic counter")
	}
	r.MessageID = "b"
	i.Accept("new", r, u)
	if i.AcceptedBytes() <= n {
		t.Fatal("new accept did not advance counter")
	}
	i.Close()
	i, e = Open(d, cfg, archive.NewMemStore())
	if e != nil {
		t.Fatal(e)
	}
	defer i.Close()
	rc, e = i.Accept(archive.IdentityKey(r), r, u)
	if e != nil || !rc.Duplicate {
		t.Fatalf("reopen identity lost %+v %v", rc, e)
	}
}

func TestCodexV4MixedConcurrentIdentity(t *testing.T) {
	d := t.TempDir()
	i, e := Open(d, config.NewAccountant(config.Default()), archive.NewMemStore())
	if e != nil {
		t.Fatal(e)
	}
	defer i.Close()
	u := config.Usage{FreeBytes: 1 << 40}
	r := archive.Record{Project: "p", MessageID: "a", Text: "same"}
	if _, e = i.Accept("legacy", r, u); e != nil {
		t.Fatal(e)
	}
	before := i.AcceptedBytes()
	next := r
	next.MessageID = "b"
	conflict := r
	conflict.Text = "different"
	start := make(chan struct{})
	results := make(chan string, 3)
	for _, item := range []struct {
		r    archive.Record
		kind string
	}{{r, "duplicate"}, {next, "new"}, {conflict, "conflict"}} {
		go func(r archive.Record, kind string) {
			<-start
			rc, e := i.Accept(archive.IdentityKey(r), r, u)
			ok := false
			switch kind {
			case "duplicate":
				ok = e == nil && rc.Duplicate
			case "new":
				ok = e == nil && !rc.Duplicate
			case "conflict":
				ok = e != nil
			}
			if ok {
				results <- "ok"
			} else {
				results <- kind
			}
		}(item.r, item.kind)
	}
	close(start)
	for j := 0; j < 3; j++ {
		if got := <-results; got != "ok" {
			t.Errorf("unexpected %s", got)
		}
	}
	if i.AcceptedBytes()-before != RecordCost(next) {
		t.Fatalf("incorrect reservation delta %d", i.AcceptedBytes()-before)
	}
	if n, e := i.AcceptedCount(); e != nil || n != 2 {
		t.Fatalf("count=%d err=%v", n, e)
	}
}
