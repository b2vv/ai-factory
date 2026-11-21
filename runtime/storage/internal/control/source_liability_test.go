package control_test

import (
	"aifactory.local/storage/internal/archive"
	"aifactory.local/storage/internal/budget"
	"aifactory.local/storage/internal/control"
	"aifactory.local/storage/internal/registry"
	"aifactory.local/storage/internal/wal"
	"errors"
	"path/filepath"
	"reflect"
	"testing"
)

func TestSourceRetryRequiresAccountingAndCommittedSourceCannotCancel(t *testing.T) {
	for _, phase := range []string{"retry-measurement", "complete-measurement", "cancel-committed"} {
		t.Run(phase, func(t *testing.T) {
			root := t.TempDir()
			d, err := control.Initialize(root)
			if err != nil {
				t.Fatal(err)
			}
			defer d.Close()
			op := registry.Principal{Kind: registry.Operator}
			if err = d.MintProject(op, "p", "fixture"); err != nil {
				t.Fatal(err)
			}
			if err = d.BeginArchiveMigration(op, "p", "g"); err != nil {
				t.Fatal(err)
			}
			var measurementError error
			l, err := budget.Initialize(filepath.Join(root, "budget.bin"), budget.Policy{LiveCap: 1 << 30}, func() (budget.Sample, error) {
				if measurementError != nil {
					return budget.Sample{}, measurementError
				}
				return budget.LocalSample(root, 1<<30)
			})
			if err != nil {
				t.Fatal(err)
			}
			if err = d.AttachBudget(l); err != nil {
				t.Fatal(err)
			}
			record := archive.Record{Project: "p", SessionID: "s", MessageID: "m", Text: "original"}
			if err = d.WithArchiveTransaction(op, "p", func(tx *control.ArchiveTransaction) error { _, err := tx.Reserve(record, nil, true); return err }); err != nil {
				t.Fatal(err)
			}
			if phase == "cancel-committed" {
				interrupted := errors.New("synthetic processing interruption")
				err = d.WithArchiveTransaction(op, "p", func(tx *control.ArchiveTransaction) error {
					return tx.Complete(record, func(archive.Envelope) error { return nil }, func() error { return interrupted })
				})
				if !errors.Is(err, interrupted) {
					t.Fatal(err)
				}
			} else {
				measurementError = errors.New("synthetic measurement unavailable")
			}
			before, _, err := d.ArchiveState("p")
			if err != nil {
				t.Fatal(err)
			}
			pending := l.Snapshot()
			frames, report, err := wal.Accepted(filepath.Join(root, "wal"))
			if err != nil || report.IsBlocked() {
				t.Fatal(err)
			}
			verified, processed := false, false
			err = d.WithArchiveTransaction(op, "p", func(tx *control.ArchiveTransaction) error {
				switch phase {
				case "retry-measurement":
					_, err := tx.Reserve(record, nil, true)
					return err
				case "complete-measurement":
					return tx.Complete(record, func(archive.Envelope) error { verified = true; return nil }, func() error { processed = true; return nil })
				default:
					return tx.Cancel(func(control.ArchiveOperation) error { verified = true; return nil }, func() error { processed = true; return nil })
				}
			})
			if phase == "cancel-committed" {
				if err == nil || !before.LastCommitted || before.CommittedOrdinal != 1 || before.Pending != nil {
					t.Fatal("committed operation cancellation admitted", before, err)
				}
			} else if !errors.Is(err, measurementError) {
				t.Fatal("accounting failure bypassed", err)
			}
			if verified || processed {
				t.Fatal("callbacks ran before accounting/commit admission", verified, processed)
			}
			after, _, readErr := d.ArchiveState("p")
			if readErr != nil || !reflect.DeepEqual(before, after) || !reflect.DeepEqual(pending, l.Snapshot()) {
				t.Fatal("refusal changed source authority or liability", readErr)
			}
			afterFrames, report, readErr := wal.Accepted(filepath.Join(root, "wal"))
			if readErr != nil || report.IsBlocked() || !reflect.DeepEqual(frames, afterFrames) {
				t.Fatal("refusal wrote authority WAL", readErr)
			}
		})
	}
}

func TestSourcePhaseRechecksAccountingAndForeignIntent(t *testing.T) {
	for _, mode := range []string{"phase-accounting", "foreign-intent"} {
		t.Run(mode, func(t *testing.T) {
			root := t.TempDir()
			d, err := control.Initialize(root)
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
			var measurementError error
			l, err := budget.Initialize(filepath.Join(root, "ledger"), budget.Policy{LiveCap: 1 << 30}, func() (budget.Sample, error) {
				if measurementError != nil {
					return budget.Sample{}, measurementError
				}
				return budget.LocalSample(root, 1<<30)
			})
			if err != nil {
				t.Fatal(err)
			}
			if err := d.AttachBudget(l); err != nil {
				t.Fatal(err)
			}
			r := archive.Record{Project: "p", SessionID: "s", MessageID: "m"}
			if err := d.WithArchiveTransaction(op, "p", func(tx *control.ArchiveTransaction) error { _, err := tx.Reserve(r, nil, true); return err }); err != nil {
				t.Fatal(err)
			}
			if mode == "foreign-intent" {
				// Deliberately corrupt cross-store binding in a fixture. Recovery must refuse.
				if err := l.Finish(); err != nil {
					t.Fatal(err)
				}
				if err := l.Reserve(budget.Evidence{Kind: "other", KeyHash: "other", PayloadHash: "other"}, 100); err != nil {
					t.Fatal(err)
				}
			}
			before, _, err := d.ArchiveState("p")
			if err != nil {
				t.Fatal(err)
			}
			liability := l.Snapshot()
			frames, rep, err := wal.Accepted(filepath.Join(root, "wal"))
			if err != nil || rep.IsBlocked() {
				t.Fatal(err)
			}
			injected := errors.New("phase accounting unavailable")
			processed := false
			err = d.WithArchiveTransaction(op, "p", func(tx *control.ArchiveTransaction) error {
				if mode == "foreign-intent" {
					_, _, err := tx.RecoveryOperation()
					return err
				}
				return tx.Complete(r, func(archive.Envelope) error { measurementError = injected; return nil }, func() error { processed = true; return nil })
			})
			if mode == "foreign-intent" {
				if !errors.Is(err, budget.ErrBlocked) {
					t.Errorf("foreign intent admitted: %v", err)
				}
			} else if !errors.Is(err, injected) {
				t.Errorf("phase accounting bypassed: %v", err)
			}
			after, _, readErr := d.ArchiveState("p")
			afterFrames, rep, walErr := wal.Accepted(filepath.Join(root, "wal"))
			if processed || readErr != nil || walErr != nil || rep.IsBlocked() || !reflect.DeepEqual(before, after) || !reflect.DeepEqual(frames, afterFrames) || !reflect.DeepEqual(liability.Pending, l.Snapshot().Pending) {
				t.Fatal("failed phase changed authority or liability", readErr, walErr)
			}
		})
	}
}
