package ingest

// Codex v5 regression (P2). The v4 durable-error accounting fix used Has(key) to detect a
// durable acceptance on the error path, but Has(key) is also true for a PRE-EXISTING record.
// A repeated opaque key carrying a DIFFERENT canonical identity returns ErrKeyConflict (nothing
// accepted) yet Has(key)=true, so the old branch wrongly seeded identHash for the REJECTED
// payload. A later retry under that identity's canonical key then falsely returned Duplicate
// with NO durable record — a silent loss. The fix accounts ONLY a genuinely new durable
// acceptance (key absent before this call, present after, error not a conflict).

import (
	"errors"
	"testing"

	"aifactory.local/storage/internal/archive"
	"aifactory.local/storage/internal/config"
	"aifactory.local/storage/internal/wal"
)

func TestReviewerV5ConflictingOpaqueKeyMustNotSeedIdentity(t *testing.T) {
	d := t.TempDir()
	i, e := Open(d, config.NewAccountant(config.Default()), archive.NewMemStore())
	if e != nil {
		t.Fatal(e)
	}
	defer i.Close()
	u := config.Usage{FreeBytes: 1 << 40}

	a := archive.Record{Project: "p", MessageID: "a", Text: "x"}
	b := archive.Record{Project: "p", MessageID: "b", Text: "y"} // different canonical identity

	// 1) First record under an opaque (legacy) key succeeds.
	if _, e := i.Accept("legacy-key", a, u); e != nil {
		t.Fatalf("first accept failed: %v", e)
	}
	// 2) SAME opaque key, DIFFERENT canonical identity -> conflict, nothing accepted.
	if _, e := i.Accept("legacy-key", b, u); !errors.Is(e, wal.ErrKeyConflict) {
		t.Fatalf("same key / different identity must conflict, got %v", e)
	}
	// 3) Retry B under its OWN canonical key must genuinely accept (NOT be falsely acknowledged
	//    as a duplicate off a poisoned identity cache).
	rc, e := i.Accept(archive.IdentityKey(b), b, u)
	if e != nil {
		t.Fatalf("canonical retry of B errored: %v", e)
	}
	if rc.Duplicate {
		t.Fatalf("rejected record falsely acknowledged as duplicate (identity cache poisoned)")
	}
	// 4) Both A and B must now be durable (two frames), so B will replay/drain.
	if n, e := i.AcceptedCount(); e != nil || n != 2 {
		t.Fatalf("expected 2 durable records (A + genuinely-accepted B), got %d (err %v)", n, e)
	}
}
