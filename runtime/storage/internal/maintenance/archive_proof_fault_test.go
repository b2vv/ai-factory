package maintenance_test

import (
	"aifactory.local/storage/internal/archive"
	"aifactory.local/storage/internal/budget"
	"aifactory.local/storage/internal/control"
	"aifactory.local/storage/internal/maintenance"
	"aifactory.local/storage/internal/registry"
	"context"
	"errors"
	"path/filepath"
	"reflect"
	"testing"
	"time"
)

type migrationProofFault struct {
	*archive.MemStore
	attachmentError error
	invalid         bool
	onLookup        func()
}

func (s *migrationProofFault) AttachMetadata(e archive.Envelope) error {
	if s.attachmentError != nil {
		return s.attachmentError
	}
	return s.MemStore.AttachMetadata(e)
}
func (s *migrationProofFault) LookupEnvelope(r archive.Record) (archive.Envelope, bool, error) {
	if s.onLookup != nil {
		s.onLookup()
	}
	e, found, err := s.MemStore.LookupEnvelope(r)
	if s.invalid && found && e.Version == 2 {
		e.Version = 99
	}
	return e, found, err
}
func TestMigrationProofFailurePreservesReservation(t *testing.T) {
	for _, mode := range []string{"attachment-error", "invalid-readback"} {
		t.Run(mode, func(t *testing.T) {
			root := t.TempDir()
			d, err := control.Initialize(filepath.Join(root, "control"))
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
			l, err := budget.Initialize(filepath.Join(root, "ledger"), budget.Policy{LiveCap: 1 << 30}, func() (budget.Sample, error) { return budget.LocalSample(root, 1<<30) })
			if err != nil {
				t.Fatal(err)
			}
			if err := d.AttachBudget(l); err != nil {
				t.Fatal(err)
			}
			source := &migrationProofFault{MemStore: archive.NewMemStore()}
			record := archive.Record{Project: "p", SessionID: "s", MessageID: "m", Text: "original"}
			if err := source.Put(record); err != nil {
				t.Fatal(err)
			}
			injected := errors.New("attachment failed")
			if mode == "attachment-error" {
				source.attachmentError = injected
			} else {
				source.invalid = true
			}
			run := func() error {
				return d.WithArchiveTransaction(op, "p", func(tx *control.ArchiveTransaction) error {
					return maintenance.MigrateArchiveSource(context.Background(), tx, source)
				})
			}
			err = run()
			if mode == "attachment-error" {
				if !errors.Is(err, injected) {
					t.Errorf("lost attachment error: %v", err)
				}
			} else {
				_, wantErr := archive.EncodeEnvelope(archive.Envelope{Version: 99})
				if err == nil || err.Error() != wantErr.Error() {
					t.Errorf("lost malformed-envelope cause: %v", err)
				}
			}
			state, _, stateErr := d.ArchiveState("p")
			if stateErr != nil {
				t.Fatal(stateErr)
			}
			if state.Pending == nil || state.CommittedOrdinal != 0 || len(l.Snapshot().Pending) != 1 {
				t.Fatal("failed proof released reservation", state)
			}
			pending := l.Snapshot().Pending
			if err := run(); err == nil {
				t.Error("retry bypassed failed proof")
			}
			again, _, err := d.ArchiveState("p")
			if err != nil || !reflect.DeepEqual(state, again) || !reflect.DeepEqual(pending, l.Snapshot().Pending) {
				t.Fatal("failed retry changed durable operation", err)
			}
			source.attachmentError = nil
			source.invalid = false
			if err := run(); err != nil {
				t.Fatal(err)
			}
			actual, found, err := source.LookupEnvelope(record)
			if err != nil || !found || actual.Record != record || !actual.Metadata.Legacy || actual.Metadata.CapturedAt != nil || len(l.Snapshot().Pending) != 0 {
				t.Fatal("retry failed to preserve historical source", err)
			}
		})
	}
}

func TestHistoricalRecoveryPreservesOperationPhase(t *testing.T) {
	for _, mode := range []string{"reserved-missing", "committed-missing", "reserved-attach-error", "committed-retry", "cancel-accounting"} {
		t.Run(mode, func(t *testing.T) {
			root := t.TempDir()
			d, err := control.Initialize(filepath.Join(root, "control"))
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
			var measureErr error
			l, err := budget.Initialize(filepath.Join(root, "ledger"), budget.Policy{LiveCap: 1 << 30}, func() (budget.Sample, error) {
				if measureErr != nil {
					return budget.Sample{}, measureErr
				}
				return budget.LocalSample(root, 1<<30)
			})
			if err != nil {
				t.Fatal(err)
			}
			if err := d.AttachBudget(l); err != nil {
				t.Fatal(err)
			}
			source := &migrationProofFault{MemStore: archive.NewMemStore()}
			record := archive.Record{Project: "p", SessionID: "s", MessageID: "m", Text: "history"}
			if err := source.Put(record); err != nil {
				t.Fatal(err)
			}
			extra := record
			extra.MessageID = "z-extra"
			hasExtra := mode == "reserved-attach-error" || mode == "committed-retry"
			if hasExtra {
				if err := source.Put(extra); err != nil {
					t.Fatal(err)
				}
			}
			injected := errors.New("historical recovery interruption")
			var envelope archive.Envelope
			err = d.WithArchiveTransaction(op, "p", func(tx *control.ArchiveTransaction) error {
				var err error
				envelope, err = tx.Reserve(record, nil, true)
				if err != nil {
					return err
				}
				if mode == "committed-missing" || mode == "committed-retry" {
					if err := source.AttachMetadata(envelope); err != nil {
						return err
					}
					err = tx.Complete(record, func(archive.Envelope) error { return nil }, func() error { return injected })
					if !errors.Is(err, injected) {
						t.Fatal("prepare incomplete processing", err)
					}
				}
				return nil
			})
			if err != nil {
				t.Fatal(err)
			}
			switch mode {
			case "reserved-missing", "committed-missing", "cancel-accounting":
				if _, err := source.Purge("p", "s"); err != nil {
					t.Fatal(err)
				}
			case "reserved-attach-error":
				source.attachmentError = injected
			}
			if mode == "cancel-accounting" {
				source.onLookup = func() { measureErr = injected }
			}
			before, _, err := d.ArchiveState("p")
			if err != nil {
				t.Fatal(err)
			}
			pending := l.Snapshot().Pending
			run := func() error {
				ctx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
				defer cancel()
				return d.WithArchiveTransaction(op, "p", func(tx *control.ArchiveTransaction) error {
					return maintenance.MigrateArchiveSource(ctx, tx, source)
				})
			}
			err = run()
			failed := mode == "committed-missing" || mode == "reserved-attach-error" || mode == "cancel-accounting"
			if failed {
				if mode == "committed-missing" {
					if !errors.Is(err, archive.ErrIDConflict) {
						t.Errorf("lost missing committed source refusal: %v", err)
					}
				} else if !errors.Is(err, injected) {
					t.Errorf("lost recovery failure: %v", err)
				}
				after, _, readErr := d.ArchiveState("p")
				if readErr != nil || !reflect.DeepEqual(before, after) || !reflect.DeepEqual(pending, l.Snapshot().Pending) {
					t.Fatal("failed recovery changed authority/liability", readErr)
				}
			} else if err != nil || len(l.Snapshot().Pending) != 0 {
				t.Fatal("successful recovery did not complete", err)
			}
			if mode == "committed-retry" {
				extraEnvelope, found, err := source.LookupEnvelope(extra)
				if err != nil || !found || extraEnvelope.Version != 2 || extraEnvelope.Metadata.Ordinal != 2 {
					t.Fatal("successful recovery returned before following source migration", extraEnvelope, found, err)
				}
			}
			if mode == "committed-missing" {
				return
			} // Never recreate a committed deleted source.
			source.onLookup = nil
			measureErr = nil
			source.attachmentError = nil
			if err := run(); err != nil {
				t.Fatal("retry", err)
			}
			if len(l.Snapshot().Pending) != 0 {
				t.Fatal("retry retained liability")
			}
			if hasExtra {
				extraEnvelope, found, err := source.LookupEnvelope(extra)
				if err != nil || !found || extraEnvelope.Version != 2 || extraEnvelope.Metadata.Ordinal != 2 || extraEnvelope.Record != extra {
					t.Fatal("recovered operation skipped remaining source page", extraEnvelope, found, err)
				}
			}
			actual, found, err := source.LookupEnvelope(record)
			if err != nil {
				t.Fatal(err)
			}
			if mode == "reserved-missing" || mode == "cancel-accounting" {
				if found {
					t.Fatal("cancelled missing source resurrected")
				}
			} else if !found || !reflect.DeepEqual(actual, envelope) {
				t.Fatal("recovery changed historical envelope")
			}
		})
	}
}
