package ingest

import (
	"path/filepath"
	"testing"

	"aifactory.local/storage/internal/archive"
	"aifactory.local/storage/internal/config"
	"aifactory.local/storage/internal/control"
	"aifactory.local/storage/internal/registry"
)

func op() registry.Principal { return registry.Principal{ID: "op", Kind: registry.Operator} }

// buffered record accepted while the archive is DOWN, then consent revoked (or a deletion
// barrier set), then a full restart (control replay + ingest reopen) + drain. The now
// archive-committed stale record must NOT be served, and a later re-grant of consent must
// NOT resurrect it.
func TestStaleRecordDoesNotBypassRevocationAcrossRestart(t *testing.T) {
	state := t.TempDir()
	ctlDir := filepath.Join(state, "control")
	ingDir := filepath.Join(state, "ingest", "wal")

	ctl, err := control.Initialize(ctlDir)
	if err != nil {
		t.Fatalf("control.Initialize: %v", err)
	}
	if err := ctl.MintProject(op(), "proj-A", "A"); err != nil {
		t.Fatal(err)
	}
	e1, err := ctl.SetConsent(op(), "proj-A", "synthetic", "capture", true) // epoch 1, enabled
	if err != nil {
		t.Fatal(err)
	}

	store := archive.NewMemStore()
	ing, err := Open(ingDir, config.NewAccountant(config.Default()), store)
	if err != nil {
		t.Fatal(err)
	}

	// Archive DOWN: accept into the WAL (durable), drain fails closed, record buffered.
	store.SetAvailable(false)
	rec := msg("proj-A", "s", "m1", "history under consent e1")
	rec.Provider, rec.SourceInstance, rec.ConsentEpoch = "synthetic", "inst-1", e1
	if _, err := ing.Accept("k1", rec, bigUsage()); err != nil {
		t.Fatalf("accept while archive down: %v", err)
	}
	if _, err := ing.Drain(); err != archive.ErrUnavailable {
		t.Fatalf("drain with archive down must fail closed, got %v", err)
	}

	// Operator revokes consent (epoch 2; RevokedThrough=2), persisted via the control WAL.
	if _, err := ctl.SetConsent(op(), "proj-A", "synthetic", "capture", false); err != nil {
		t.Fatal(err)
	}

	// RESTART: close and reopen control (replay reconstructs RevokedThrough) and the ingestor.
	ctl.Close()
	ing.Close()
	ctl2, err := control.Open(ctlDir)
	if err != nil {
		t.Fatalf("control.Open (restart): %v", err)
	}
	defer ctl2.Close()
	ing2, err := Open(ingDir, config.NewAccountant(config.Default()), store)
	if err != nil {
		t.Fatal(err)
	}
	defer ing2.Close()

	// Archive recovers; draining through the serve-gate must QUARANTINE (NOT publish) the
	// now-revoked buffered record (PLAN §11.1: pre-revocation items are not published).
	store.SetAvailable(true)
	gate := func(r archive.Record) bool {
		return len(ctl2.Retention().Serve([]archive.Record{r}, "capture")) == 1
	}
	if _, err := ing2.DrainGated(gate); err != nil {
		t.Fatalf("gated drain after restart/recovery: %v", err)
	}
	if n := len(store.All("proj-A")); n != 0 {
		t.Fatalf("revoked buffered record must NOT be published to the archive, got %d", n)
	}

	// Re-granting consent (epoch 3) must NOT resurrect or publish the e1 record.
	if _, err := ctl2.SetConsent(op(), "proj-A", "synthetic", "capture", true); err != nil {
		t.Fatal(err)
	}
	if _, err := ing2.DrainGated(gate); err != nil {
		t.Fatal(err)
	}
	if n := len(store.All("proj-A")); n != 0 {
		t.Fatalf("re-granting consent resurrected revoked data (published %d)", n)
	}
	if served := ctl2.Retention().Serve(store.All("proj-A"), "capture"); len(served) != 0 {
		t.Fatalf("serve-gate must also withhold any revoked-era record: served %d", len(served))
	}
}

// Physical purge: a published record is PHYSICALLY erased from the archive after a deletion
// barrier, and cannot resurrect via a WAL re-drain or a backup restore (both gate on the
// retained barrier). Quarantine/serve-gate hiding is NOT sufficient; the bytes are gone.
func TestPurgePhysicallyErasesAndNoResurrection(t *testing.T) {
	state := t.TempDir()
	ctlDir := filepath.Join(state, "control")
	ingDir := filepath.Join(state, "ingest", "wal")
	ctl, err := control.Initialize(ctlDir)
	if err != nil {
		t.Fatal(err)
	}
	defer ctl.Close()
	if err := ctl.MintProject(op(), "proj-A", "A"); err != nil {
		t.Fatal(err)
	}
	e1, _ := ctl.SetConsent(op(), "proj-A", "synthetic", "capture", true)

	store := archive.NewMemStore()
	ing, err := Open(ingDir, config.NewAccountant(config.Default()), store)
	if err != nil {
		t.Fatal(err)
	}
	defer ing.Close()
	rec := msg("proj-A", "s", "m1", "to be physically deleted")
	rec.Provider, rec.SourceInstance, rec.ConsentEpoch = "synthetic", "inst-1", e1
	if _, err := ing.Accept("k1", rec, bigUsage()); err != nil {
		t.Fatal(err)
	}
	gate := func(r archive.Record) bool {
		return len(ctl.Retention().Serve([]archive.Record{r}, "capture")) == 1
	}
	if _, err := ing.DrainGated(gate); err != nil { // consent on -> published
		t.Fatal(err)
	}
	if len(store.All("proj-A")) != 1 {
		t.Fatalf("record must be published before deletion")
	}
	backup := append([]archive.Record(nil), store.All("proj-A")...) // snapshot "backup"

	// Deletion barrier (tombstone), then PHYSICAL purge of BOTH stores.
	if _, err := ctl.DeleteProjectBarrier(op(), "proj-A"); err != nil {
		t.Fatal(err)
	}
	// (archive half) Mongo/MemStore copy physically removed.
	if n, err := store.Purge("proj-A", ""); err != nil || n != 1 {
		t.Fatalf("purge must physically remove 1 record, got (%d,%v)", n, err)
	}
	if len(store.All("proj-A")) != 0 {
		t.Fatalf("record must be PHYSICALLY gone from the archive after purge")
	}
	// (WAL half) the intake-journal frame is physically erased too (crash-safe Compact), so the
	// payload is absent from BOTH live stores - not merely hidden by the serve-gate.
	if out, err := ing.Compact(func(r archive.Record) bool { return r.Project != "proj-A" }); err != nil || out.Dropped != 1 || out.ResidualUnparseable != 0 {
		t.Fatalf("WAL compaction must drop exactly the purged frame with no residual, got (%+v,%v)", out, err)
	}
	if c, err := ing.AcceptedCount(); err != nil || c != 0 {
		t.Fatalf("WAL must physically hold no proj-A frame after compaction: count=%d err=%v", c, err)
	}
	// Non-resurrection via WAL re-drain: the frame is gone AND the retained barrier denies republish.
	if _, err := ing.DrainGated(gate); err != nil {
		t.Fatal(err)
	}
	if len(store.All("proj-A")) != 0 {
		t.Fatalf("purged record resurrected via WAL re-drain")
	}
	// Non-resurrection via backup restore: the retained barrier withholds it (agreed contract -
	// Restore re-applies barriers+current consent before serving a stale backup).
	if restored := ctl.Retention().Restore(backup, "capture"); len(restored) != 0 {
		t.Fatalf("purged record resurrected via backup restore: %d", len(restored))
	}
}

// Same shape but with a project deletion barrier instead of consent revocation: the stale
// record, once drained, is still withheld by the barrier across restart.
func TestStaleRecordDoesNotBypassDeletionBarrierAcrossRestart(t *testing.T) {
	state := t.TempDir()
	ctlDir := filepath.Join(state, "control")
	ingDir := filepath.Join(state, "ingest", "wal")

	ctl, err := control.Initialize(ctlDir)
	if err != nil {
		t.Fatal(err)
	}
	if err := ctl.MintProject(op(), "proj-A", "A"); err != nil {
		t.Fatal(err)
	}
	e1, _ := ctl.SetConsent(op(), "proj-A", "synthetic", "capture", true)

	store := archive.NewMemStore()
	ing, err := Open(ingDir, config.NewAccountant(config.Default()), store)
	if err != nil {
		t.Fatal(err)
	}
	store.SetAvailable(false)
	rec := msg("proj-A", "s", "m1", "history to be deleted")
	rec.Provider, rec.SourceInstance, rec.ConsentEpoch = "synthetic", "inst-1", e1
	if _, err := ing.Accept("k1", rec, bigUsage()); err != nil {
		t.Fatal(err)
	}
	_, _ = ing.Drain()

	// Operator sets a project deletion barrier, persisted via the control WAL.
	if _, err := ctl.DeleteProjectBarrier(op(), "proj-A"); err != nil {
		t.Fatal(err)
	}
	ctl.Close()
	ing.Close()

	ctl2, err := control.Open(ctlDir)
	if err != nil {
		t.Fatal(err)
	}
	defer ctl2.Close()
	ing2, err := Open(ingDir, config.NewAccountant(config.Default()), store)
	if err != nil {
		t.Fatal(err)
	}
	defer ing2.Close()
	store.SetAvailable(true)
	gate := func(r archive.Record) bool {
		return len(ctl2.Retention().Serve([]archive.Record{r}, "capture")) == 1
	}
	if _, err := ing2.DrainGated(gate); err != nil {
		t.Fatal(err)
	}
	if n := len(store.All("proj-A")); n != 0 {
		t.Fatalf("a record under a deletion barrier must NOT be published to the archive, got %d", n)
	}
}
