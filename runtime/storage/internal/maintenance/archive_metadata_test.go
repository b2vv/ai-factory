package maintenance_test

import (
	"aifactory.local/storage/internal/archive"
	"aifactory.local/storage/internal/budget"
	"aifactory.local/storage/internal/control"
	"aifactory.local/storage/internal/maintenance"
	"aifactory.local/storage/internal/registry"
	"aifactory.local/storage/internal/search"
	"context"
	"errors"
	"fmt"
	"path/filepath"
	"testing"
)

func TestArchiveSourceMigrationRestartsWithoutChangingIdentity(t *testing.T) {
	root := t.TempDir()
	d, err := control.Initialize(filepath.Join(root, "control"))
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
	l, err := budget.Initialize(filepath.Join(root, "ledger"), budget.Policy{LiveCap: 1 << 30}, func() (budget.Sample, error) { return budget.LocalSample(root, 1<<30) })
	if err != nil {
		t.Fatal(err)
	}
	if err := d.AttachBudget(l); err != nil {
		t.Fatal(err)
	}
	source := &migrationFault{MemStore: archive.NewMemStore(), failAt: 17}
	before := map[string]string{}
	for n := 0; n < 103; n++ {
		r := archive.Record{Project: "p", SourceInstance: fmt.Sprint(n % 2), SessionID: "s", MessageID: fmt.Sprint(n), Text: "original"}
		if err := source.Put(r); err != nil {
			t.Fatal(err)
		}
		before[archive.IdentityKey(r)] = search.RecordHash(r)
	}
	run := func() error {
		return d.WithArchiveTransaction(op, "p", func(tx *control.ArchiveTransaction) error {
			return maintenance.MigrateArchiveSource(context.Background(), tx, source)
		})
	}
	if err := run(); err == nil {
		t.Fatal("injected attachment failure missing")
	}
	state, _, err := d.ArchiveState("p")
	if err != nil || state.Pending == nil || state.CommittedOrdinal != 16 {
		t.Fatal(state, err)
	}
	source.failAt = 0
	if err := run(); err != nil {
		t.Fatal("restart", err)
	}
	if err := run(); err != nil {
		t.Fatal("idempotent retry", err)
	}
	state, _, err = d.ArchiveState("p")
	if err != nil || state.Pending != nil || state.CommittedOrdinal != 103 || state.NextOrdinal != 104 || state.MigrationComplete {
		t.Fatal(state, err)
	}
	records, err := source.Fetch("p")
	if err != nil {
		t.Fatal(err)
	}
	for _, r := range records {
		if search.RecordHash(r) != before[archive.IdentityKey(r)] {
			t.Fatal("historical identity/content changed")
		}
		e, found, err := source.LookupEnvelope(r)
		if err != nil || !found || !e.Metadata.Legacy || e.Metadata.CapturedAt != nil || e.Metadata.SourceEventTime != nil || e.Metadata.Generation != "g" {
			t.Fatal(e, found, err)
		}
	}
	if len(l.Snapshot().Pending) != 0 {
		t.Fatal("migration leaked reservation")
	}
}

type migrationFault struct {
	*archive.MemStore
	failAt, calls int
}

func (s *migrationFault) AttachMetadata(e archive.Envelope) error {
	s.calls++
	if s.calls == s.failAt {
		return errors.New("fixture interruption")
	}
	return s.MemStore.AttachMetadata(e)
}

func (s *migrationFault) Scan(project string, after *archive.Position) (archive.Window, error) {
	w, err := s.MemStore.Scan(project, after)
	if len(w.Records) > 7 {
		w.Records = w.Records[:7]
		w.More = true
	}
	return w, err
}
