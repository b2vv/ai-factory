package control_test

import (
	"aifactory.local/storage/internal/archive"
	"aifactory.local/storage/internal/budget"
	"aifactory.local/storage/internal/control"
	"aifactory.local/storage/internal/registry"
	"errors"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

func TestArchiveTransactionRetainsReservationAndCommitAcrossRestart(t *testing.T) {
	dir := t.TempDir()
	d, err := control.Initialize(dir)
	if err != nil {
		t.Fatal(err)
	}
	op := registry.Principal{ID: "op", Kind: registry.Operator}
	if err := d.MintProject(op, "p", "project"); err != nil {
		t.Fatal(err)
	}
	if err := d.BeginArchiveMigration(op, "p", "generation"); err != nil {
		t.Fatal(err)
	}
	attachArchiveLedger(t, d, dir)
	r := archive.Record{Project: "p", SessionID: "s", MessageID: "m", Text: "legacy"}
	var first archive.Envelope
	interrupted := errors.New("simulated interruption")
	err = d.WithArchiveTransaction(op, "p", func(tx *control.ArchiveTransaction) error {
		var e error
		first, e = tx.Reserve(r, nil, true)
		if e != nil {
			return e
		}
		return interrupted
	})
	if !errors.Is(err, interrupted) || first.Metadata.Ordinal != 1 || first.Metadata.CapturedAt != nil || !first.Metadata.Legacy {
		t.Fatal(first, err)
	}
	if err := d.Close(); err != nil {
		t.Fatal(err)
	}
	d, err = control.Open(dir)
	if err != nil {
		t.Fatal(err)
	}
	attachArchiveLedger(t, d, dir)
	defer d.Close()
	err = d.WithArchiveTransaction(op, "p", func(tx *control.ArchiveTransaction) error {
		other := r
		other.MessageID = "o"
		if _, e := tx.Reserve(other, nil, true); e == nil {
			t.Fatal("pending reservation overtaken")
		}
		again, e := tx.Reserve(r, nil, true)
		if e != nil {
			return e
		}
		if again.Metadata.Ordinal != first.Metadata.Ordinal || again.Metadata.Generation != first.Metadata.Generation {
			t.Fatal("retry changed reservation", again)
		}
		called := false
		if e := tx.Complete(r, func(archive.Envelope) error { return interrupted }, func() error { called = true; return nil }); !errors.Is(e, interrupted) || called {
			t.Fatal("commit before verified projection", e, called)
		}
		return tx.Complete(r, func(e archive.Envelope) error {
			if e.Record != r {
				t.Fatal("record changed")
			}
			return nil
		}, func() error { return nil })
	})
	if err != nil {
		t.Fatal(err)
	}
	s, ok, err := d.ArchiveState("p")
	if err != nil || !ok || s.NextOrdinal != 2 || s.CommittedOrdinal != 1 {
		t.Fatal(s, ok, err)
	}
	if _, err := d.DeleteProjectBarrier(op, "p"); err != nil {
		t.Fatal(err)
	}
	s, _, err = d.ArchiveState("p")
	if err != nil || s.CommittedOrdinal != 1 {
		t.Fatal("delete reduced committed high-water", s, err)
	}
}

func TestArchiveTransactionBudgetRetainsCompletionHeadroom(t *testing.T) {
	dir := t.TempDir()
	d, err := control.Initialize(dir)
	if err != nil {
		t.Fatal(err)
	}
	defer d.Close()
	op := registry.Principal{ID: "op", Kind: registry.Operator}
	if err := d.MintProject(op, "p", "project"); err != nil {
		t.Fatal(err)
	}
	if err := d.BeginArchiveMigration(op, "p", "g"); err != nil {
		t.Fatal(err)
	}
	sample := func() (budget.Sample, error) { return budget.LocalSample(dir, 1<<30) }
	l, err := budget.Initialize(filepath.Join(dir, "budget.bin"), budget.Policy{LiveCap: 1 << 30}, sample)
	if err != nil {
		t.Fatal(err)
	}
	if err := d.AttachBudget(l); err != nil {
		t.Fatal(err)
	}
	r := archive.Record{Project: "p", SessionID: "s", MessageID: "a", Text: "one"}
	var planned int64
	fail := errors.New("interrupted processing")
	if err := d.WithArchiveTransaction(op, "p", func(tx *control.ArchiveTransaction) error {
		if _, err := tx.Reserve(r, nil, true); err != nil {
			return err
		}
		pending := l.Snapshot().Pending
		if len(pending) != 1 || pending[0].Evidence.Kind != "archive-source-v2" {
			t.Fatal(pending)
		}
		planned = pending[0].Bytes
		return tx.Complete(r, func(archive.Envelope) error { return nil }, func() error { return fail })
	}); !errors.Is(err, fail) {
		t.Fatal(err)
	}
	// Committed but unprocessed: the original liability survives and blocks overtaking.
	if len(l.Snapshot().Pending) != 1 {
		t.Fatal("completion liability lost")
	}
	if err := d.WithArchiveTransaction(op, "p", func(tx *control.ArchiveTransaction) error {
		next := r
		next.MessageID = "b"
		_, err := tx.Reserve(next, nil, true)
		return err
	}); err == nil {
		t.Fatal("unprocessed commit overtaken")
	}
	if err := d.WithArchiveTransaction(op, "p", func(tx *control.ArchiveTransaction) error {
		return tx.Complete(r, func(archive.Envelope) error { return nil }, func() error { return nil })
	}); err != nil {
		t.Fatal(err)
	}
	if len(l.Snapshot().Pending) != 0 {
		t.Fatal("verified completion not released")
	}
	var used int64
	for _, n := range l.Snapshot().Components {
		used += n
	}
	if err := l.Configure(budget.Policy{LiveCap: used + planned - 1}); err != nil {
		t.Fatal(err)
	}
	next := r
	next.MessageID = "b"
	if err := d.WithArchiveTransaction(op, "p", func(tx *control.ArchiveTransaction) error { _, err := tx.Reserve(next, nil, true); return err }); err == nil {
		t.Fatal("one-byte-short accepted")
	}
	state, _, err := d.ArchiveState("p")
	if err != nil || state.NextOrdinal != 2 || state.Pending != nil {
		t.Fatal("refusal allocated ordinal", state, err)
	}
	if err := l.Configure(budget.Policy{LiveCap: used + planned}); err != nil {
		t.Fatal(err)
	}
	if err := d.WithArchiveTransaction(op, "p", func(tx *control.ArchiveTransaction) error {
		if _, err := tx.Reserve(next, nil, true); err != nil {
			return err
		}
		return tx.Complete(next, func(archive.Envelope) error { return nil }, func() error { return nil })
	}); err != nil {
		t.Fatal("exact-fit could not finish", err)
	}
}

func TestArchiveMigrationCompletionAndTimeReservation(t *testing.T) {
	dir := t.TempDir()
	d, err := control.Initialize(dir)
	if err != nil {
		t.Fatal(err)
	}
	defer d.Close()
	op := registry.Principal{ID: "op", Kind: registry.Operator}
	if err := d.MintProject(op, "p", "project"); err != nil {
		t.Fatal(err)
	}
	if err := d.BeginArchiveMigration(op, "p", "g"); err != nil {
		t.Fatal(err)
	}
	attachArchiveLedger(t, d, dir)
	r := archive.Record{Project: "p", SessionID: "s", MessageID: "m"}
	fail := errors.New("index not rebuilt")
	event := time.Date(2020, 1, 1, 0, 0, 0, 123, time.FixedZone("offset", 7200))
	before := time.Now().UTC()
	var reserved archive.Envelope
	if err := d.WithArchiveTransaction(op, "p", func(tx *control.ArchiveTransaction) error {
		if _, err := tx.Reserve(r, &event, false); err == nil {
			t.Fatal("writer active before migration complete")
		}
		if err := tx.FinishMigration(func(control.ArchiveState) error { return fail }); !errors.Is(err, fail) {
			t.Fatal(err)
		}
		if err := tx.FinishMigration(func(s control.ArchiveState) error {
			if s.Generation != "g" || s.MigrationComplete {
				t.Fatal(s)
			}
			return nil
		}); err != nil {
			return err
		}
		var err error
		reserved, err = tx.Reserve(r, &event, false)
		return err
	}); err != nil {
		t.Fatal(err)
	}
	if reserved.Metadata.CapturedAt == nil || reserved.Metadata.CapturedAt.Before(before) || reserved.Metadata.CapturedAt.After(time.Now().UTC()) || !reserved.Metadata.SourceEventTime.Equal(event) {
		t.Fatal(reserved)
	}
	// Caller-owned times and returned envelopes must not mutate durable state.
	fixedCapture := *reserved.Metadata.CapturedAt
	fixedEvent := *reserved.Metadata.SourceEventTime
	*reserved.Metadata.CapturedAt = event
	*reserved.Metadata.SourceEventTime = before
	if err := d.WithArchiveTransaction(op, "p", func(tx *control.ArchiveTransaction) error {
		retry, err := tx.Reserve(r, nil, false)
		if err != nil {
			return err
		}
		if !retry.Metadata.CapturedAt.Equal(fixedCapture) || !retry.Metadata.SourceEventTime.Equal(fixedEvent) {
			t.Fatal("reservation aliased caller", retry)
		}
		unequal := fixedEvent.Add(time.Second)
		if _, err := tx.Reserve(r, &unequal, false); err == nil {
			t.Fatal("contradictory known source time accepted")
		}
		return tx.Complete(r, func(archive.Envelope) error { return nil }, func() error { return nil })
	}); err != nil {
		t.Fatal(err)
	}
	if err := d.Close(); err != nil {
		t.Fatal(err)
	}
	d, err = control.Open(dir)
	if err != nil {
		t.Fatal(err)
	}
	attachArchiveLedger(t, d, dir)
	defer d.Close()
	state, _, err := d.ArchiveState("p")
	if err != nil || !state.MigrationComplete || state.CommittedOrdinal != 1 {
		t.Fatal(state, err)
	}
	previous := state.PolicyRevision
	if _, err := d.SetConsent(op, "p", "synthetic", "capture", true); err != nil {
		t.Fatal(err)
	}
	state, _, err = d.ArchiveState("p")
	if err != nil || state.PolicyRevision <= previous {
		t.Fatal("policy did not invalidate freshness", state, err)
	}
	previous = state.PolicyRevision
	if _, err := d.DeleteSessionBarrier(op, "p", "s"); err != nil {
		t.Fatal(err)
	}
	state, _, err = d.ArchiveState("p")
	if err != nil || state.PolicyRevision <= previous || state.CommittedOrdinal != 1 {
		t.Fatal("deletion checkpoint invalid", state, err)
	}
}

func TestArchiveTransactionRequiresSharedLedger(t *testing.T) {
	d, err := control.Initialize(t.TempDir())
	if err != nil {
		t.Fatal(err)
	}
	defer d.Close()
	op := registry.Principal{Kind: registry.Operator}
	if err := d.MintProject(op, "p", "fixture"); err != nil {
		t.Fatal(err)
	}
	if err := d.BeginArchiveMigration(op, "p", "g"); err != nil {
		t.Fatal(err)
	}
	called := false
	if err := d.WithArchiveTransaction(op, "p", func(*control.ArchiveTransaction) error { called = true; return nil }); err == nil || called {
		t.Fatal("transaction started without durable liability", err, called)
	}
}

func attachArchiveLedger(t *testing.T, d *control.Durable, dir string) {
	t.Helper()
	path := filepath.Join(dir, "budget.bin")
	sample := func() (budget.Sample, error) { return budget.LocalSample(dir, 1<<30) }
	var l *budget.Ledger
	var err error
	if _, e := os.Stat(path); os.IsNotExist(e) {
		l, err = budget.Initialize(path, budget.Policy{LiveCap: 1 << 30}, sample)
	} else {
		l, err = budget.Open(path, sample)
	}
	if err != nil {
		t.Fatal(err)
	}
	if err := d.AttachBudget(l); err != nil {
		t.Fatal(err)
	}
}

func TestArchiveCancellationRequiresProofAndNeverCommitsSource(t *testing.T) {
	dir := t.TempDir()
	d, err := control.Initialize(dir)
	if err != nil {
		t.Fatal(err)
	}
	defer d.Close()
	op := registry.Principal{Kind: registry.Operator}
	if err := d.MintProject(op, "p", "fixture"); err != nil {
		t.Fatal(err)
	}
	if err := d.BeginArchiveMigration(op, "p", "g"); err != nil {
		t.Fatal(err)
	}
	attachArchiveLedger(t, d, dir)
	r := archive.Record{Project: "p", SessionID: "s", MessageID: "m"}
	ambiguous := errors.New("ambiguous WAL")
	if err := d.WithArchiveTransaction(op, "p", func(tx *control.ArchiveTransaction) error {
		if _, err := tx.Reserve(r, nil, true); err != nil {
			return err
		}
		if err := tx.Cancel(func(control.ArchiveOperation) error { return ambiguous }, func() error { t.Fatal("processed ambiguous state"); return nil }); !errors.Is(err, ambiguous) {
			t.Fatal(err)
		}
		return nil
	}); err != nil {
		t.Fatal(err)
	}
	if err := d.Close(); err != nil {
		t.Fatal(err)
	}
	d, err = control.Open(dir)
	if err != nil {
		t.Fatal(err)
	}
	defer d.Close()
	attachArchiveLedger(t, d, dir)
	if err := d.WithArchiveTransaction(op, "p", func(tx *control.ArchiveTransaction) error {
		return tx.Cancel(func(o control.ArchiveOperation) error {
			if o.Identity.MessageID != "m" || o.Metadata.Ordinal != 1 {
				t.Fatal(o)
			}
			return nil
		}, func() error { return nil })
	}); err != nil {
		t.Fatal(err)
	}
	state, _, err := d.ArchiveState("p")
	if err != nil || state.Pending != nil || state.CommittedOrdinal != 0 || state.NextOrdinal != 2 {
		t.Fatal(state, err)
	}
	if err := d.WithArchiveTransaction(op, "p", func(tx *control.ArchiveTransaction) error {
		return tx.Complete(r, func(archive.Envelope) error { return nil }, func() error { return nil })
	}); err == nil {
		t.Fatal("cancel treated as commit")
	}
	next := r
	next.MessageID = "next"
	if err := d.WithArchiveTransaction(op, "p", func(tx *control.ArchiveTransaction) error {
		e, err := tx.Reserve(next, nil, true)
		if err == nil && e.Metadata.Ordinal != 2 {
			t.Fatal(e)
		}
		return err
	}); err != nil {
		t.Fatal(err)
	}
}

func TestArchiveRecoveryDistinguishesOrphanIntentFromReservedSource(t *testing.T) {
	dir := t.TempDir()
	d, err := control.Initialize(dir)
	if err != nil {
		t.Fatal(err)
	}
	defer d.Close()
	op := registry.Principal{Kind: registry.Operator}
	if err := d.MintProject(op, "p", "fixture"); err != nil {
		t.Fatal(err)
	}
	if err := d.BeginArchiveMigration(op, "p", "g"); err != nil {
		t.Fatal(err)
	}
	attachArchiveLedger(t, d, dir)
	if err := d.Budget().Reserve(budget.Evidence{Kind: "archive-source-v2", KeyHash: strings.Repeat("a", 64), PayloadHash: strings.Repeat("b", 64)}, 1024); err != nil {
		t.Fatal(err)
	}
	if err := d.Close(); err != nil {
		t.Fatal(err)
	}
	d, err = control.Open(dir)
	if err != nil {
		t.Fatal(err)
	}
	defer d.Close()
	attachArchiveLedger(t, d, dir)
	if err := d.RecoverUnreservedArchiveIntent(op); err != nil {
		t.Fatal("clean no-reserve intent not released", err)
	}
	if len(d.Budget().Snapshot().Pending) != 0 {
		t.Fatal("orphan liability remains")
	}
	r := archive.Record{Project: "p", SessionID: "s", MessageID: "m"}
	if err := d.WithArchiveTransaction(op, "p", func(tx *control.ArchiveTransaction) error { _, err := tx.Reserve(r, nil, true); return err }); err != nil {
		t.Fatal(err)
	}
	if err := d.RecoverUnreservedArchiveIntent(op); err == nil {
		t.Fatal("reserved source liability erased")
	}
	if len(d.Budget().Snapshot().Pending) != 1 {
		t.Fatal("reserved liability lost")
	}
}

func TestArchiveWriterUsesOneAuthorityFenceForLegacyAndMetadata(t *testing.T) {
	dir := t.TempDir()
	d, err := control.Initialize(dir)
	if err != nil {
		t.Fatal(err)
	}
	defer d.Close()
	op := registry.Principal{Kind: registry.Operator}
	if err := d.MintProject(op, "p", "fixture"); err != nil {
		t.Fatal(err)
	}
	if err := d.WithArchiveWriter(op, "p", func(tx *control.ArchiveTransaction) error {
		if tx != nil {
			t.Fatal("unactivated project changed path")
		}
		return nil
	}); err != nil {
		t.Fatal(err)
	}
	if err := d.BeginArchiveMigration(op, "p", "g"); err != nil {
		t.Fatal(err)
	}
	attachArchiveLedger(t, d, dir)
	var escaped *control.ArchiveTransaction
	if err := d.WithArchiveWriter(op, "p", func(tx *control.ArchiveTransaction) error {
		if tx == nil {
			t.Fatal("activated project used legacy path")
		}
		escaped = tx
		s, err := tx.State()
		if err != nil || s.Generation != "g" || s.MigrationComplete {
			t.Fatal(s, err)
		}
		return nil
	}); err != nil {
		t.Fatal(err)
	}
	if _, err := escaped.State(); err == nil {
		t.Fatal("authority used after fence released")
	}
}

func TestArchiveRecoveryOperationTracksOnlyOwnedIntent(t *testing.T) {
	dir := t.TempDir()
	d, err := control.Initialize(dir)
	if err != nil {
		t.Fatal(err)
	}
	defer d.Close()
	op := registry.Principal{Kind: registry.Operator}
	if err := d.MintProject(op, "p", "p"); err != nil {
		t.Fatal(err)
	}
	if err := d.BeginArchiveMigration(op, "p", "g"); err != nil {
		t.Fatal(err)
	}
	attachArchiveLedger(t, d, dir)
	r := archive.Record{Project: "p", SessionID: "s", MessageID: "m"}
	if err := d.WithArchiveTransaction(op, "p", func(tx *control.ArchiveTransaction) error {
		if operation, _, err := tx.RecoveryOperation(); err != nil || operation != nil {
			t.Fatal(operation, err)
		}
		if _, err := tx.Reserve(r, nil, true); err != nil {
			return err
		}
		operation, phase, err := tx.RecoveryOperation()
		if err != nil || operation == nil || phase != "reserved" {
			t.Fatal(operation, phase, err)
		}
		operation.Metadata.Ordinal = 99
		again, _, err := tx.RecoveryOperation()
		if err != nil || again.Metadata.Ordinal != 1 {
			t.Fatal("aliased recovery", again, err)
		}
		interrupted := errors.New("processing interrupted")
		if err := tx.Complete(r, func(archive.Envelope) error { return nil }, func() error { return interrupted }); !errors.Is(err, interrupted) {
			t.Fatal(err)
		}
		_, phase, err = tx.RecoveryOperation()
		if err != nil || phase != "committed" {
			t.Fatal(phase, err)
		}
		if err := tx.Complete(r, func(archive.Envelope) error { return nil }, func() error { return nil }); err != nil {
			return err
		}
		if operation, _, err := tx.RecoveryOperation(); err != nil || operation != nil {
			t.Fatal("finished receipt reported pending", operation, err)
		}
		return nil
	}); err != nil {
		t.Fatal(err)
	}
}
