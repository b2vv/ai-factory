package ingest

import (
	"os"
	"path/filepath"
	"testing"

	"aifactory.local/storage/internal/archive"
	"aifactory.local/storage/internal/config"
)

// TestQuarantinedRecordStaysAccountedThenCompacted is the end-to-end manageability proof for a
// quarantined record (item: a skipped record must not become unmanageable):
//
//  1. a proj-B record publishes; a proj-A record is QUARANTINED by the publish gate (not
//     published) while the checkpoint advances past BOTH;
//  2. the quarantined record is STILL durably accounted after the checkpoint moved (it is a
//     full WAL frame; AcceptedCount sees it) and SURVIVES a restart (reopen re-derives it);
//  3. physical purge FINDS it via Compact and erases its WAL bytes, preserving proj-B; the
//     watermark is clamped down so the (now shorter) journal never trips the corruption guard;
//  4. after compaction + restart the proj-A record cannot resurrect through a re-drain, and
//     proj-B is not re-published (its seq is already at/under the clamped checkpoint).
func TestQuarantinedRecordStaysAccountedThenCompacted(t *testing.T) {
	dir := filepath.Join(t.TempDir(), "wal")
	store := archive.NewMemStore()
	open := func() *Ingestor {
		ing, err := Open(dir, config.NewAccountant(config.Default()), store)
		if err != nil {
			t.Fatalf("open: %v", err)
		}
		return ing
	}

	ing := open()
	// proj-B gets the LOWER WAL seq, proj-A the higher, so dropping proj-A forces a watermark clamp.
	recB := msg("proj-B", "s", "mB", "keep me")
	recB.SourceInstance = "inst-B"
	recA := msg("proj-A", "s", "mA", "quarantine then erase me")
	recA.SourceInstance = "inst-A"
	if _, err := ing.Accept("kB", recB, bigUsage()); err != nil {
		t.Fatalf("accept B: %v", err)
	}
	if _, err := ing.Accept("kA", recA, bigUsage()); err != nil {
		t.Fatalf("accept A: %v", err)
	}

	// Gate publishes proj-B, quarantines proj-A (simulates a deletion barrier / revocation on A).
	gate := func(r archive.Record) bool { return r.Project == "proj-B" }
	n, err := ing.DrainGated(gate)
	if err != nil || n != 1 {
		t.Fatalf("drain: published=%d err=%v (want 1 published, A quarantined)", n, err)
	}
	if got := len(store.All("proj-A")); got != 0 {
		t.Fatalf("quarantined proj-A must NOT be published, archive has %d", got)
	}
	if got := len(store.All("proj-B")); got != 1 {
		t.Fatalf("proj-B must be published, archive has %d", got)
	}
	// (2) Quarantined record still accounted AFTER the checkpoint advanced past it.
	if c, err := ing.AcceptedCount(); err != nil || c != 2 {
		t.Fatalf("both records must remain durably accounted after drain: count=%d err=%v", c, err)
	}
	ing.Close()

	// (2) Survives a restart: reopen re-derives the identical accepted set, quarantined record included.
	ing = open()
	if c, err := ing.AcceptedCount(); err != nil || c != 2 {
		t.Fatalf("quarantined record must survive restart: count=%d err=%v", c, err)
	}

	// (3) Purge finds and physically erases proj-A via Compact; proj-B is preserved.
	out, err := ing.Compact(func(r archive.Record) bool { return r.Project != "proj-A" })
	if err != nil || out.Dropped != 1 || out.ResidualUnparseable != 0 {
		t.Fatalf("compact must drop exactly proj-A with no residual: %+v err=%v", out, err)
	}
	if c, err := ing.AcceptedCount(); err != nil || c != 1 {
		t.Fatalf("after compaction only proj-B remains: count=%d err=%v", c, err)
	}
	ing.Close()

	// (4) After compaction + restart: proj-A stays gone; re-drain cannot resurrect it, and
	// proj-B is not re-published (checkpoint was clamped but still covers proj-B's seq).
	ing = open()
	defer ing.Close()
	if c, err := ing.AcceptedCount(); err != nil || c != 1 {
		t.Fatalf("proj-A must stay physically erased across restart: count=%d err=%v", c, err)
	}
	n2, err := ing.DrainGated(gate)
	if err != nil {
		t.Fatalf("re-drain after compaction: %v", err)
	}
	if n2 != 0 {
		t.Fatalf("no record should (re)publish after compaction: got %d", n2)
	}
	if got := len(store.All("proj-A")); got != 0 {
		t.Fatalf("proj-A must not resurrect via re-drain after physical erasure, archive has %d", got)
	}
}

// TestCompactRefusesBlockedIngestWAL: the ingestor must not compact (physically delete) a WAL
// whose recovery is BLOCKED; the ambiguous tail is preserved, not resolved by erasure.
func TestCompactRefusesBlockedIngestWAL(t *testing.T) {
	dir := filepath.Join(t.TempDir(), "wal")
	store := archive.NewMemStore()
	ing, err := Open(dir, config.NewAccountant(config.Default()), store)
	if err != nil {
		t.Fatalf("open: %v", err)
	}
	if _, err := ing.Accept("k1", msg("p", "s", "m1", "x"), bigUsage()); err != nil {
		t.Fatalf("accept: %v", err)
	}
	ing.Close()

	// Corrupt the accepts journal tail -> recovery BLOCKED.
	accPath := filepath.Join(dir, "accepts")
	f, _ := os.OpenFile(accPath, os.O_WRONLY|os.O_APPEND, 0o600)
	_, _ = f.Write([]byte("GARBAGE!!"))
	f.Close()

	ing2, err := Open(dir, config.NewAccountant(config.Default()), store)
	if err != nil {
		t.Fatalf("reopen: %v", err)
	}
	defer ing2.Close()
	if _, err := ing2.Compact(func(archive.Record) bool { return false }); err == nil {
		t.Fatalf("Compact must refuse a BLOCKED ingest WAL")
	}
}
