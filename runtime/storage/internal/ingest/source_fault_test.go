package ingest_test

import (
	"aifactory.local/storage/internal/wal"
	"encoding/json"
	"errors"
	"os"
	"path/filepath"
	"reflect"
	"testing"

	"aifactory.local/storage/internal/archive"
	"aifactory.local/storage/internal/budget"
	"aifactory.local/storage/internal/config"
	"aifactory.local/storage/internal/control"
	"aifactory.local/storage/internal/ingest"
	"aifactory.local/storage/internal/registry"
)

type faultyEnvelopeSource struct {
	*archive.MemStore
	putErr, lookupErr error
	invalid           bool
}

func (s *faultyEnvelopeSource) PutEnvelope(e archive.Envelope) error {
	if s.putErr != nil {
		return s.putErr
	}
	return s.MemStore.PutEnvelope(e)
}
func (s *faultyEnvelopeSource) LookupEnvelope(r archive.Record) (archive.Envelope, bool, error) {
	if s.lookupErr != nil {
		return archive.Envelope{}, false, s.lookupErr
	}
	e, found, err := s.MemStore.LookupEnvelope(r)
	if s.invalid && found {
		e.Version = 99
	}
	return e, found, err
}

func TestSourceFaultsRetainExactLiabilityAndRetry(t *testing.T) {
	for _, mode := range []string{"write-error", "unaccepted-lookup-error", "committed-lookup-error", "committed-invalid-envelope"} {
		t.Run(mode, func(t *testing.T) {
			root := t.TempDir()
			ctl, err := control.Initialize(root)
			if err != nil {
				t.Fatal(err)
			}
			defer ctl.Close()
			op := registry.Principal{Kind: registry.Operator}
			if err := ctl.MintProject(op, "p", "fixture"); err != nil {
				t.Fatal(err)
			}
			if err := ctl.BeginArchiveMigration(op, "p", "g"); err != nil {
				t.Fatal(err)
			}
			ledger, err := budget.Initialize(filepath.Join(root, "budget.bin"), budget.Policy{LiveCap: 1 << 30}, func() (budget.Sample, error) { return budget.LocalSample(root, 1<<30) })
			if err != nil {
				t.Fatal(err)
			}
			if err := ctl.AttachBudget(ledger); err != nil {
				t.Fatal(err)
			}
			source := &faultyEnvelopeSource{MemStore: archive.NewMemStore()}
			intake, err := ingest.Open(filepath.Join(root, "intake"), config.NewAccountant(config.Default()), source)
			if err != nil {
				t.Fatal(err)
			}
			defer intake.Close()
			if err := intake.SetBudget(ledger); err != nil {
				t.Fatal(err)
			}
			r := archive.Record{Project: "p", SourceInstance: "source", SessionID: "s", MessageID: "m", Text: "preserve"}
			injected := errors.New("source fixture failure")
			err = ctl.WithArchiveTransaction(op, "p", func(tx *control.ArchiveTransaction) error {
				if err := tx.FinishMigration(func(control.ArchiveState) error { return nil }); err != nil {
					return err
				}
				e, err := tx.Reserve(r, nil, false)
				if err != nil {
					return err
				}
				if mode != "unaccepted-lookup-error" {
					if _, err := intake.AcceptEnvelope(e); err != nil {
						return err
					}
				}
				if mode == "committed-lookup-error" || mode == "committed-invalid-envelope" {
					if err := source.PutEnvelope(e); err != nil {
						return err
					}
					if err := tx.Complete(r, func(archive.Envelope) error { return nil }, func() error { return injected }); !errors.Is(err, injected) {
						t.Fatalf("prepare interrupted processing: %v", err)
					}
				}
				frames, report, readErr := wal.Accepted(filepath.Join(root, "wal"))
				if readErr != nil || report.IsBlocked() {
					t.Fatal(readErr)
				}
				rawMeta, readErr := os.ReadFile(filepath.Join(root, "control.meta"))
				if readErr != nil {
					t.Fatal(readErr)
				}
				var meta struct {
					HighWater uint64 `json:"high_water"`
				}
				if err := json.Unmarshal(rawMeta, &meta); err != nil {
					t.Fatal(err)
				}
				if meta.HighWater != wal.MaxSeq(frames) {
					t.Fatal("source operation acknowledged beyond durable high-water", meta.HighWater, wal.MaxSeq(frames))
				}
				beforeState, err := tx.State()
				if err != nil {
					return err
				}
				before := ledger.Snapshot()
				switch mode {
				case "write-error":
					source.putErr = injected
				case "unaccepted-lookup-error", "committed-lookup-error":
					source.lookupErr = injected
				case "committed-invalid-envelope":
					source.invalid = true
				}
				if mode == "write-error" {
					_, err = intake.CommitEnvelope(tx, e)
				} else {
					err = intake.RecoverEnvelope(tx, func(archive.Record) bool { return true })
				}
				if mode == "committed-invalid-envelope" {
					bad := e
					bad.Version = 99
					_, wantErr := archive.EncodeEnvelope(bad)
					if err == nil || err.Error() != wantErr.Error() {
						t.Errorf("lost malformed-envelope cause: %v", err)
					}
				} else if !errors.Is(err, injected) {
					t.Errorf("lost exact source failure: %v", err)
				}
				afterState, stateErr := tx.State()
				if stateErr != nil {
					return stateErr
				}
				if !reflect.DeepEqual(beforeState, afterState) || !reflect.DeepEqual(before.Pending, ledger.Snapshot().Pending) {
					t.Fatal("failed source proof changed operation or liability")
				}
				source.putErr = nil
				source.lookupErr = nil
				source.invalid = false
				if err := intake.RecoverEnvelope(tx, func(archive.Record) bool { return true }); err != nil {
					return err
				}
				if len(ledger.Snapshot().Pending) != 0 {
					t.Fatal("successful recovery retained liability")
				}
				got, found, err := source.LookupEnvelope(r)
				if err != nil {
					return err
				}
				if mode == "unaccepted-lookup-error" {
					if found {
						t.Fatal("unaccepted operation created source")
					}
				} else {
					if !found || !reflect.DeepEqual(e, got) {
						t.Fatal("retry changed source envelope")
					}
				}
				return nil
			})
			if err != nil {
				t.Fatal(err)
			}
		})
	}
}
