package ingest

// Regression tests derived from the Codex review (2026-10-31) findings R2/R3/R4, kept as
// permanent safety assertions. Where the original probe encoded the BROKEN assumption (that an
// over-cap accept should succeed, or that a raw wal.Compact without checkpoint coordination
// should recover), the regression asserts the CORRECT fixed invariant instead of the broken
// behavior — it is NOT fitted to a broken implementation.

import (
	"encoding/json"
	"os"
	"path/filepath"
	"sync"
	"testing"

	"aifactory.local/storage/internal/archive"
	"aifactory.local/storage/internal/config"
	"aifactory.local/storage/internal/wal"
)

// R2 (verbatim intent): a repeated idempotency key with a DIFFERENT payload must surface a
// conflict, never be acknowledged as a benign duplicate.
func TestReviewConflictingReplay(t *testing.T) {
	s := archive.NewMemStore()
	i, e := Open(t.TempDir(), config.NewAccountant(config.Default()), s)
	if e != nil {
		t.Fatal(e)
	}
	defer i.Close()
	u := config.Usage{FreeBytes: 1 << 40}
	r := archive.Record{Project: "p", MessageID: "m", Text: "original"}
	if _, e := i.Accept("key", r, u); e != nil {
		t.Fatal(e)
	}
	i.Drain()
	r.Text = "edited"
	if _, e := i.Accept("key", r, u); e == nil {
		t.Fatalf("conflicting payload silently accepted; stored=%q", s.All("p")[0].Text)
	}
}

// R3-A: with a cap SMALLER than one record's true persistent cost, admission must REJECT the
// accept (backpressure) and write nothing — the physical WAL cap is never exceeded. (The
// original probe set cap = JSON payload length and asserted the journal stayed within cap; the
// fixed, correct behavior at that cap is rejection, which this asserts.)
func TestReviewPhysicalWALCapRejectsBelowCost(t *testing.T) {
	d := t.TempDir()
	r := archive.Record{Project: "p", MessageID: "m", Text: "payload"}
	b, _ := json.Marshal(r)
	c := config.Default()
	c.WALBytes = int64(len(b)) // < true cost (frame+key+intent+accept+idx)
	i, e := Open(d, config.NewAccountant(c), archive.NewMemStore())
	if e != nil {
		t.Fatal(e)
	}
	defer i.Close()
	if _, e := i.Accept("key", r, config.Usage{FreeBytes: 1 << 40}); e == nil {
		t.Fatalf("accept must be rejected when the full cost exceeds the WAL cap")
	}
	if n := journalSize(t, d); n > c.WALBytes {
		t.Fatalf("rejected accept must write nothing: journal=%d cap=%d", n, c.WALBytes)
	}
}

// R3-B: at a cap sized to EXACTLY one record's true cost, one accept fits and a second
// (distinct key) is rejected; the first record is never evicted and the cap is never exceeded.
func TestReviewPhysicalWALCapExactFitThenReject(t *testing.T) {
	d := t.TempDir()
	r1 := archive.Record{Project: "p", MessageID: "m1", Text: "one"}
	b1, _ := json.Marshal(r1)
	cost := wal.RecordCost("k1", b1)
	c := config.Default()
	c.WALBytes = cost
	i, e := Open(d, config.NewAccountant(c), archive.NewMemStore())
	if e != nil {
		t.Fatal(e)
	}
	defer i.Close()
	if _, e := i.Accept("k1", r1, config.Usage{FreeBytes: 1 << 40}); e != nil {
		t.Fatalf("first record must fit at an exact-cost cap: %v", e)
	}
	if _, e := i.Accept("k2", archive.Record{Project: "p", MessageID: "m2", Text: "two"}, config.Usage{FreeBytes: 1 << 40}); e == nil {
		t.Fatalf("second record must be rejected (cap full), never evicting the first")
	}
	if n := journalSize(t, d); n > c.WALBytes {
		t.Fatalf("WAL cap exceeded: journal=%d cap=%d", n, c.WALBytes)
	}
	if cnt, _ := i.AcceptedCount(); cnt != 1 {
		t.Fatalf("first accepted record must remain (never evicted), got %d", cnt)
	}
}

// R3 concurrency: N concurrent accepts (distinct keys) against a cap sized for exactly K
// records must admit exactly K and reject the rest, with the journal never exceeding the cap —
// no two requests admit against the same remaining capacity.
func TestReviewConcurrentAdmissionAtCapBoundary(t *testing.T) {
	d := t.TempDir()
	// The probe record MUST match the concurrent records byte-for-byte (3-char key used as the
	// 3-char MessageID, same Project/Text) so every record has the identical persistent cost.
	probe := archive.Record{Project: "p", MessageID: "kAa", Text: "sized"}
	pb, _ := json.Marshal(probe)
	perRecord := wal.RecordCost("kAa", pb)
	const K = 5
	c := config.Default()
	c.WALBytes = perRecord * K
	i, e := Open(d, config.NewAccountant(c), archive.NewMemStore())
	if e != nil {
		t.Fatal(e)
	}
	defer i.Close()
	const N = 40
	var wg sync.WaitGroup
	var mu sync.Mutex
	ok := 0
	for n := 0; n < N; n++ {
		wg.Add(1)
		go func(n int) {
			defer wg.Done()
			key := string([]byte{'k', byte('A' + n/26), byte('a' + n%26)})
			rec := archive.Record{Project: "p", MessageID: key, Text: "sized"}
			if _, err := i.Accept(key, rec, config.Usage{FreeBytes: 1 << 40}); err == nil {
				mu.Lock()
				ok++
				mu.Unlock()
			}
		}(n)
	}
	wg.Wait()
	if ok != K {
		t.Fatalf("exactly %d of %d concurrent accepts should be admitted, got %d", K, N, ok)
	}
	if n := journalSize(t, d); n > c.WALBytes {
		t.Fatalf("concurrent accepts exceeded the WAL cap: journal=%d cap=%d", n, c.WALBytes)
	}
}

// R4 (via the atomic ingest.Compact path): compaction clamps the checkpoint as part of the
// transition, so a reopen after compaction drains cleanly (never misreads committed>MaxSeq as
// corruption). Also a NEW record accepted after a tail-delete is drained (not skipped by a
// stale watermark).
func TestReviewCompactThenRestartDrainsAndAcceptsTail(t *testing.T) {
	d := t.TempDir()
	s := archive.NewMemStore()
	u := config.Usage{FreeBytes: 1 << 40}
	i, e := Open(d, config.NewAccountant(config.Default()), s)
	if e != nil {
		t.Fatal(e)
	}
	if _, e := i.Accept("a", archive.Record{Project: "a", MessageID: "a"}, u); e != nil {
		t.Fatal(e)
	}
	if _, e := i.Accept("b", archive.Record{Project: "b", MessageID: "b"}, u); e != nil {
		t.Fatal(e)
	}
	if _, e := i.Drain(); e != nil {
		t.Fatal(e)
	}
	// Atomic compaction: drop project "b" (the tail seq), clamping the checkpoint first.
	if out, e := i.Compact(func(r archive.Record) bool { return r.Project != "b" }); e != nil || out.Dropped != 1 {
		t.Fatalf("compact: %+v err=%v", out, e)
	}
	i.Close()

	// Restart: reopen and drain — must NOT fail closed with a corrupt-checkpoint error.
	i2, e := Open(d, config.NewAccountant(config.Default()), s)
	if e != nil {
		t.Fatal(e)
	}
	defer i2.Close()
	if _, e := i2.Drain(); e != nil {
		t.Fatalf("valid compacted generation must drain after restart: %v", e)
	}
	// A new record accepted after the tail-delete must drain (not skipped by the old watermark).
	if _, e := i2.Accept("c", archive.Record{Project: "a", MessageID: "c"}, u); e != nil {
		t.Fatal(e)
	}
	n, e := i2.Drain()
	if e != nil || n != 1 {
		t.Fatalf("newly accepted post-compaction record must drain: n=%d err=%v", n, e)
	}
}

// R5 (unit-level of the worker's drain path): a record accepted while the archive is DOWN is
// drained on recovery by a drain call WITHOUT any new Accept (the background worker calls the
// same DrainGated). No producer retry is required to project the queued record.
func TestReviewRecoveryDrainsWithoutNewProducerRequest(t *testing.T) {
	d := t.TempDir()
	s := archive.NewMemStore()
	i, e := Open(d, config.NewAccountant(config.Default()), s)
	if e != nil {
		t.Fatal(e)
	}
	defer i.Close()
	s.SetAvailable(false)
	if _, e := i.Accept("k", archive.Record{Project: "p", MessageID: "m", Text: "queued"}, config.Usage{FreeBytes: 1 << 40}); e != nil {
		t.Fatal(e)
	}
	if _, e := i.Drain(); e != archive.ErrUnavailable {
		t.Fatalf("drain with archive down must fail closed, got %v", e)
	}
	// Archive recovers; a drain (the worker's path) projects the record with NO new Accept.
	s.SetAvailable(true)
	n, e := i.Drain()
	if e != nil || n != 1 {
		t.Fatalf("recovery drain (no new producer request) must project the queued record: n=%d err=%v", n, e)
	}
	if len(s.All("p")) != 1 {
		t.Fatalf("queued record must be archived after recovery drain")
	}
}

func journalSize(t *testing.T, dir string) int64 {
	t.Helper()
	var n int64
	for _, name := range []string{"data", "intents", "accepts", "committed.idx"} {
		if fi, err := os.Stat(filepath.Join(dir, name)); err == nil {
			n += fi.Size()
		}
	}
	return n
}
