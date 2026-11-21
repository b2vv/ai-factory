package ingest

// Combination coverage requested after the Codex v3 review: concurrency mixed with error
// paths (conflict + benign duplicate + new), not just happy paths. Run under -race.

import (
	"encoding/json"
	"path/filepath"
	"sync"
	"testing"

	"aifactory.local/storage/internal/archive"
	"aifactory.local/storage/internal/config"
	"aifactory.local/storage/internal/wal"
)

// TestV3ComboConcurrentMixedOutcomes fires many concurrent accepts that mix: (a) distinct new
// identities, (b) byte-identical replays of a seeded identity (benign duplicate no-op), and
// (c) same-identity/different-payload conflicts. A tight WAL cap bounds how many NEW records
// fit. Invariants: conflicts are rejected (ErrKeyConflict), duplicates never append a frame,
// new records admit only up to the cap, the physical WAL cap is never exceeded, and the
// accepted count equals the seeded record plus the admitted-new count (no over-admission, no
// race under -race).
func TestV3ComboConcurrentMixedOutcomes(t *testing.T) {
	d := filepath.Join(t.TempDir(), "wal")
	// Size the cap for exactly K new records on top of the seed (all records share a shape).
	shape := archive.Record{Project: "p", SourceInstance: "i", SessionID: "s", MessageID: "seed", Text: "x"}
	sb, _ := json.Marshal(shape)
	per := wal.RecordCost(archive.IdentityKey(shape), sb)
	const K = 6
	cfg := config.Default()
	cfg.WALBytes = per * (K + 1) // seed + K new
	store := archive.NewMemStore()
	i, err := Open(d, config.NewAccountant(cfg), store)
	if err != nil {
		t.Fatal(err)
	}
	defer i.Close()
	u := config.Usage{FreeBytes: 1 << 40}

	// Seed one record (identity "seed").
	if _, err := i.Accept(archive.IdentityKey(shape), shape, u); err != nil {
		t.Fatal(err)
	}

	var wg sync.WaitGroup
	var mu sync.Mutex
	conflicts, dups, news := 0, 0, 0
	fire := func(kind string, n int) {
		defer wg.Done()
		switch kind {
		case "dup": // byte-identical replay of the seed -> duplicate no-op
			rc, err := i.Accept(archive.IdentityKey(shape), shape, u)
			if err == nil && rc.Duplicate {
				mu.Lock()
				dups++
				mu.Unlock()
			}
		case "conflict": // same identity as seed, different payload -> conflict
			r := shape
			r.Text = "different"
			if _, err := i.Accept(archive.IdentityKey(r), r, u); err == wal.ErrKeyConflict {
				mu.Lock()
				conflicts++
				mu.Unlock()
			}
		default: // distinct new identity
			r := archive.Record{Project: "p", SourceInstance: "i", SessionID: "s", MessageID: kind, Text: "x"}
			if _, err := i.Accept(archive.IdentityKey(r), r, u); err == nil {
				mu.Lock()
				news++
				mu.Unlock()
			}
		}
	}
	for n := 0; n < 10; n++ {
		wg.Add(3)
		go fire("dup", n)
		go fire("conflict", n)
		go fire(string(rune('A'+n)), n) // distinct new identities A..J
	}
	wg.Wait()

	if conflicts != 10 {
		t.Fatalf("every conflicting replay must be rejected: got %d/10", conflicts)
	}
	if dups != 10 {
		t.Fatalf("every byte-identical replay must be a duplicate no-op: got %d/10", dups)
	}
	if news != K {
		t.Fatalf("new records must admit exactly up to the cap: got %d, want %d", news, K)
	}
	if cnt, _ := i.AcceptedCount(); cnt != K+1 {
		t.Fatalf("accepted frames must be seed+K=%d, got %d (no over-admission)", K+1, cnt)
	}
	if jb, _ := i.w.Bytes(); jb > cfg.WALBytes {
		t.Fatalf("physical WAL cap exceeded under concurrency: %d > %d", jb, cfg.WALBytes)
	}
}
