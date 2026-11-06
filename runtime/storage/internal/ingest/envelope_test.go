package ingest_test

import (
	"aifactory.local/storage/internal/archive"
	"aifactory.local/storage/internal/budget"
	"aifactory.local/storage/internal/config"
	"aifactory.local/storage/internal/control"
	"aifactory.local/storage/internal/ingest"
	"aifactory.local/storage/internal/registry"
	"aifactory.local/storage/internal/wal"
	"errors"
	"os"
	"os/exec"
	"path/filepath"
	"syscall"
	"testing"
	"time"
)

func TestVersionedIntakeReceiptAndPurgePreserveIdentity(t *testing.T) {
	dir := t.TempDir()
	w, err := wal.Open(dir)
	if err != nil {
		t.Fatal(err)
	}
	now := time.Date(2026, 11, 5, 12, 0, 0, 1, time.UTC)
	e := archive.Envelope{Version: 2, Record: archive.Record{Project: "p", SourceInstance: "source", SessionID: "s", MessageID: "m", Text: "original"}, Metadata: archive.Metadata{Generation: "g", Ordinal: 1, CapturedAt: &now}}
	raw, err := archive.EncodeEnvelope(e)
	if err != nil {
		t.Fatal(err)
	}
	if _, err := w.AcceptV2(archive.IdentityKey(e.Record), raw); err != nil {
		t.Fatal(err)
	}
	if err := w.Close(); err != nil {
		t.Fatal(err)
	}
	store := archive.NewMemStore()
	i, err := ingest.Open(dir, config.NewAccountant(config.Default()), store)
	if err != nil {
		t.Fatal(err)
	}
	defer i.Close()
	st, err := i.RecordState(archive.IdentityKey(e.Record), "p")
	if err != nil || st.State != "durable_accepted" {
		t.Fatal(st, err)
	}
	if _, err := i.Drain(); err == nil {
		t.Fatal("legacy drain consumed metadata transaction")
	}
	if got, _ := store.Fetch("p"); len(got) != 0 {
		t.Fatal("legacy drain projected source", got)
	}
	if got, _ := store.Fetch(""); len(got) != 0 {
		t.Fatal("envelope decoded as zero Record", got)
	}
	outcome, err := i.Compact(func(r archive.Record) bool { return r.Project != "p" })
	if err != nil || outcome.Dropped != 1 || outcome.ResidualUnparseable != 0 {
		t.Fatal(outcome, err)
	}
	n, err := i.AcceptedCount()
	if err != nil || n != 0 {
		t.Fatal(n, err)
	}
}

func TestVersionedPendingInventoryRequiresExactMetadata(t *testing.T) {
	dir := t.TempDir()
	w, err := wal.Open(dir)
	if err != nil {
		t.Fatal(err)
	}
	now := time.Date(2026, 11, 5, 12, 0, 0, 1, time.UTC)
	e := archive.Envelope{Version: 2, Record: archive.Record{Project: "p", SessionID: "s", MessageID: "m", Text: "original"}, Metadata: archive.Metadata{Generation: "g", Ordinal: 1, CapturedAt: &now}}
	raw, err := archive.EncodeEnvelope(e)
	if err != nil {
		t.Fatal(err)
	}
	if _, err := w.AcceptV2(archive.IdentityKey(e.Record), raw); err != nil {
		t.Fatal(err)
	}
	if err := w.Close(); err != nil {
		t.Fatal(err)
	}
	empty := archive.NewMemStore()
	before, err := ingest.PendingLogicalBytes(dir, 1<<30, empty)
	if err != nil || before <= archive.ReservationBytes(e.Record)+64 {
		t.Fatal("metadata projection liability missing", before, err)
	}
	if err := empty.Put(e.Record); err != nil {
		t.Fatal(err)
	}
	if _, err := ingest.PendingLogicalBytes(dir, 1<<30, empty); err == nil {
		t.Fatal("legacy record discharged v2 metadata liability")
	}
	exact := archive.NewMemStore()
	if err := exact.PutEnvelope(e); err != nil {
		t.Fatal(err)
	}
	after, err := ingest.PendingLogicalBytes(dir, 1<<30, exact)
	if err != nil || after != 64 {
		t.Fatal("exact source did not discharge projection debt", after, err)
	}
}

func TestControlOwnedEnvelopeTransactionReplaysExactSource(t *testing.T) {
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
	l, err := budget.Initialize(filepath.Join(root, "budget.bin"), budget.Policy{LiveCap: 1 << 30}, func() (budget.Sample, error) { return budget.LocalSample(root, 1<<30) })
	if err != nil {
		t.Fatal(err)
	}
	if err := ctl.AttachBudget(l); err != nil {
		t.Fatal(err)
	}
	store := &changingEnvelopeStore{MemStore: archive.NewMemStore()}
	dir := filepath.Join(root, "intake")
	i, err := ingest.Open(dir, config.NewAccountant(config.Default()), store)
	if err != nil {
		t.Fatal(err)
	}
	defer i.Close()
	if err := i.SetBudget(l); err != nil {
		t.Fatal(err)
	}
	r := archive.Record{Project: "p", SessionID: "s", MessageID: "m", Text: "original"}
	var envelope archive.Envelope
	if err := ctl.WithArchiveTransaction(op, "p", func(tx *control.ArchiveTransaction) error {
		if err := tx.FinishMigration(func(control.ArchiveState) error { return nil }); err != nil {
			return err
		}
		var err error
		envelope, err = tx.Reserve(r, nil, false)
		if err != nil {
			return err
		}
		receipt, err := i.AcceptEnvelope(envelope)
		if err != nil {
			return err
		}
		if receipt.Duplicate || receipt.Seq == 0 {
			t.Fatal(receipt)
		}
		again, err := i.AcceptEnvelope(envelope)
		if err != nil || !again.Duplicate || again.Seq != receipt.Seq {
			t.Fatal(again, err)
		}
		changed := envelope
		changed.Metadata.Ordinal++
		if _, err := i.AcceptEnvelope(changed); err == nil {
			t.Fatal("unowned envelope accepted")
		}
		return nil // simulated crash after durable acceptance
	}); err != nil {
		t.Fatal(err)
	}
	if err := i.Close(); err != nil {
		t.Fatal(err)
	}
	i, err = ingest.Open(dir, config.NewAccountant(config.Default()), store)
	if err != nil {
		t.Fatal(err)
	}
	defer i.Close()
	if err := i.SetBudget(l); err != nil {
		t.Fatal(err)
	}
	if err := ctl.WithArchiveTransaction(op, "p", func(tx *control.ArchiveTransaction) error {
		e, err := tx.Reserve(r, nil, false)
		if err != nil {
			return err
		}
		if !e.Metadata.CapturedAt.Equal(*envelope.Metadata.CapturedAt) {
			t.Fatal("restarted acceptance changed time")
		}
		_, err = i.CommitEnvelope(tx, e)
		return err
	}); err != nil {
		t.Fatal(err)
	}
	state, _, err := ctl.ArchiveState("p")
	if err != nil || state.CommittedOrdinal != 1 || len(l.Snapshot().Pending) != 0 {
		t.Fatal(state, err)
	}
	receipt, err := i.RecordState(archive.IdentityKey(r), "p")
	if err != nil || receipt.State != "archive_committed" {
		t.Fatal(receipt, err)
	}
	store.wrong = true
	if _, err := i.RecordState(archive.IdentityKey(r), "p"); err == nil {
		t.Fatal("metadata mismatch reported committed")
	}
	if _, err := i.Reclaim(); err == nil {
		t.Fatal("metadata mismatch allowed reclamation")
	}
	store.wrong = false
	outcome, err := i.Reclaim()
	if err != nil || outcome.Dropped != 1 {
		t.Fatal("exact metadata not reclaimed", outcome, err)
	}
	got, found, err := store.LookupEnvelope(r)
	if err != nil || !found || got.Record != r || !got.Metadata.CapturedAt.Equal(*envelope.Metadata.CapturedAt) {
		t.Fatal("reclamation changed source", got, found, err)
	}
}

type changingEnvelopeStore struct {
	*archive.MemStore
	wrong bool
}

func (s *changingEnvelopeStore) LookupEnvelope(r archive.Record) (archive.Envelope, bool, error) {
	e, found, err := s.MemStore.LookupEnvelope(r)
	if s.wrong && found {
		e.Metadata.Ordinal++
	}
	return e, found, err
}

func TestEnvelopeDurableAcceptanceErrorRetainsAccounting(t *testing.T) {
	// A real unprivileged filesystem denial occurs after the accepted frame is
	// durable. Root would bypass mode bits, so only the isolated test child drops UID.
	if os.Geteuid() == 0 {
		exe, err := os.Executable()
		if err != nil {
			t.Fatal(err)
		}
		raw, err := os.ReadFile(exe)
		if err != nil {
			t.Fatal(err)
		}
		fixture, err := os.MkdirTemp("", "envelope-child-")
		if err != nil {
			t.Fatal(err)
		}
		defer os.RemoveAll(fixture)
		if err := os.Chmod(fixture, 0755); err != nil {
			t.Fatal(err)
		}
		executable := filepath.Join(fixture, "ingest.test")
		if err := os.WriteFile(executable, raw, 0755); err != nil {
			t.Fatal(err)
		}
		cmd := exec.Command(executable, "-test.run=^TestEnvelopeDurableAcceptanceErrorRetainsAccounting$", "-test.v")
		cmd.SysProcAttr = &syscall.SysProcAttr{Credential: &syscall.Credential{Uid: 65534, Gid: 65534}}
		out, err := cmd.CombinedOutput()
		if err != nil {
			t.Fatalf("unprivileged fixture: %s (%v)", out, err)
		}
		return
	}
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
	l, err := budget.Initialize(filepath.Join(root, "budget.bin"), budget.Policy{LiveCap: 1 << 30}, func() (budget.Sample, error) { return budget.LocalSample(root, 1<<30) })
	if err != nil {
		t.Fatal(err)
	}
	if err := ctl.AttachBudget(l); err != nil {
		t.Fatal(err)
	}
	dir := filepath.Join(root, "intake")
	i, err := ingest.Open(dir, config.NewAccountant(config.Default()), archive.NewMemStore())
	if err != nil {
		t.Fatal(err)
	}
	defer i.Close()
	if err := i.SetBudget(l); err != nil {
		t.Fatal(err)
	}
	r := archive.Record{Project: "p", SessionID: "s", MessageID: "m"}
	if err := ctl.WithArchiveTransaction(op, "p", func(tx *control.ArchiveTransaction) error {
		if err := tx.FinishMigration(func(control.ArchiveState) error { return nil }); err != nil {
			return err
		}
		e, err := tx.Reserve(r, nil, false)
		if err != nil {
			return err
		}
		idx := filepath.Join(dir, "committed.idx")
		if err := os.WriteFile(idx, nil, 0400); err != nil {
			return err
		}
		if err := os.Chmod(idx, 0400); err != nil {
			return err
		}
		receipt, err := i.AcceptEnvelope(e)
		if err == nil || receipt.Seq == 0 {
			t.Fatalf("not a durable acceptance failure: %+v %v", receipt, err)
		}
		accepted, reserved, debt := i.AcceptedBytes(), i.ReservationBytes(), i.PendingArchiveBytes()
		if accepted <= 0 || reserved <= 0 || debt <= 0 {
			t.Fatalf("durable error lost accounting: %d %d %d", accepted, reserved, debt)
		}
		if err := os.Chmod(idx, 0600); err != nil {
			return err
		}
		again, err := i.AcceptEnvelope(e)
		if err != nil || !again.Duplicate {
			t.Fatal(again, err)
		}
		if i.AcceptedBytes() != accepted || i.ReservationBytes() != reserved || i.PendingArchiveBytes() != debt {
			t.Fatal("duplicate retry changed accounted liability")
		}
		return nil
	}); err != nil {
		t.Fatal(err)
	}
}

func TestMetadataOpenRequiresExistingWAL(t *testing.T) {
	dir := t.TempDir()
	store := archive.NewMemStore()
	acct := config.NewAccountant(config.Default())
	i, err := ingest.Open(dir, acct, store)
	if err != nil {
		t.Fatal(err)
	}
	i.Close()
	i, err = ingest.OpenExisting(dir, acct, store)
	if err != nil {
		t.Fatal("initialized empty intake refused", err)
	}
	i.Close()
	if err := os.Remove(filepath.Join(dir, "accepts")); err != nil {
		t.Fatal(err)
	}
	if i, err := ingest.OpenExisting(dir, acct, store); err == nil {
		i.Close()
		t.Fatal("missing acceptance evidence initialized")
	}
	if _, err := os.Stat(filepath.Join(dir, "accepts")); !os.IsNotExist(err) {
		t.Fatal("evidence recreated", err)
	}
}

func TestAcceptedEnvelopeRecoveryEvidence(t *testing.T) {
	dir := t.TempDir()
	w, err := wal.Open(dir)
	if err != nil {
		t.Fatal(err)
	}
	now := time.Now().UTC()
	e := archive.Envelope{Version: 2, Record: archive.Record{Project: "p", SourceInstance: "a", SessionID: "s", MessageID: "m", Text: "original"}, Metadata: archive.Metadata{Generation: "g", Ordinal: 1, CapturedAt: &now}}
	raw, _ := archive.EncodeEnvelope(e)
	if _, err := w.AcceptV2(archive.IdentityKey(e.Record), raw); err != nil {
		t.Fatal(err)
	}
	w.Close()
	i, err := ingest.OpenExisting(dir, config.NewAccountant(config.Default()), archive.NewMemStore())
	if err != nil {
		t.Fatal(err)
	}
	defer i.Close()
	got, found, err := i.AcceptedEnvelope(e.Record)
	if err != nil || !found || got.Record != e.Record || got.Metadata.Ordinal != 1 {
		t.Fatal(got, found, err)
	}
	*got.Metadata.CapturedAt = now.Add(time.Hour)
	again, _, err := i.AcceptedEnvelope(e.Record)
	if err != nil || !again.Metadata.CapturedAt.Equal(now) {
		t.Fatal("aliased evidence", again, err)
	}
	other := e.Record
	other.SourceInstance = "b"
	if _, found, err := i.AcceptedEnvelope(other); err != nil || found {
		t.Fatal("source isolation", found, err)
	}
	// Missing authority must never be reported as a clean negative lookup.
	if err := os.Remove(filepath.Join(dir, "accepts")); err != nil {
		t.Fatal(err)
	}
	if _, _, err := i.AcceptedEnvelope(other); err == nil {
		t.Fatal("lost journal reported absence")
	}
}

// These failures occur after intake acceptance, so failure must retain the same
// reservation and never advance source commitment or the processing watermark.
func TestSourceTransactionRequiresExactReadback(t *testing.T) {
	for _, mode := range []string{"uncertain_success", "absent", "text", "time", "read_error"} {
		t.Run(mode, func(t *testing.T) {
			root := t.TempDir()
			ctl, err := control.Initialize(filepath.Join(root, "control"))
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
			l, err := budget.Initialize(filepath.Join(root, "budget.bin"), budget.Policy{LiveCap: 1 << 30}, func() (budget.Sample, error) { return budget.LocalSample(root, 1<<30) })
			if err != nil {
				t.Fatal(err)
			}
			if err := ctl.AttachBudget(l); err != nil {
				t.Fatal(err)
			}
			source := &sourceFault{MemStore: archive.NewMemStore(), mode: mode}
			i, err := ingest.Open(filepath.Join(root, "intake"), config.NewAccountant(config.Default()), source)
			if err != nil {
				t.Fatal(err)
			}
			defer i.Close()
			if err := i.SetBudget(l); err != nil {
				t.Fatal(err)
			}
			r := archive.Record{Project: "p", SessionID: "s", MessageID: "m", Text: "original"}
			err = ctl.WithArchiveTransaction(op, "p", func(tx *control.ArchiveTransaction) error {
				if err := tx.FinishMigration(func(control.ArchiveState) error { return nil }); err != nil {
					return err
				}
				e, err := tx.Reserve(r, nil, false)
				if err != nil {
					return err
				}
				receipt, err := i.CommitEnvelope(tx, e)
				if receipt.Seq == 0 {
					t.Fatal("fault before acceptance", err)
				}
				return err
			})
			state, _, stateErr := ctl.ArchiveState("p")
			if stateErr != nil {
				t.Fatal(stateErr)
			}
			if mode == "uncertain_success" {
				if err != nil || state.CommittedOrdinal != 1 || state.Pending != nil {
					t.Fatal(state, err)
				}
			} else {
				if err == nil || state.CommittedOrdinal != 0 || state.Pending == nil {
					t.Fatal("unproved source committed", state, err)
				}
				receipt, err := i.RecordState(archive.IdentityKey(r), "p")
				if err != nil || receipt.State != "durable_accepted" {
					t.Fatal("unproved source processed", receipt, err)
				}
				source.mode = ""
				if err := ctl.WithArchiveTransaction(op, "p", func(tx *control.ArchiveTransaction) error {
					e, err := tx.Reserve(r, nil, false)
					if err != nil {
						return err
					}
					_, err = i.CommitEnvelope(tx, e)
					return err
				}); err != nil {
					t.Fatal("retry failed", err)
				}
			}
		})
	}
}

type sourceFault struct {
	*archive.MemStore
	mode string
}

func (s *sourceFault) PutEnvelope(e archive.Envelope) error {
	if s.mode == "absent" {
		return errors.New("uncertain insert")
	}
	if err := s.MemStore.PutEnvelope(e); err != nil {
		return err
	}
	if s.mode == "uncertain_success" {
		return errors.New("uncertain insert")
	}
	return nil
}
func (s *sourceFault) LookupEnvelope(r archive.Record) (archive.Envelope, bool, error) {
	if s.mode == "read_error" {
		return archive.Envelope{}, false, errors.New("source unavailable")
	}
	e, found, err := s.MemStore.LookupEnvelope(r)
	if found && s.mode == "text" {
		e.Record.Text = "changed"
	}
	if found && s.mode == "time" {
		*e.Metadata.CapturedAt = e.Metadata.CapturedAt.Add(time.Nanosecond)
	}
	return e, found, err
}

func TestRecoverEnvelopeCompletesOrCancelsOwnedOperation(t *testing.T) {
	for _, phase := range []string{"reserved", "accepted", "projected", "committed", "cancelled", "revoked"} {
		t.Run(phase, func(t *testing.T) {
			root := t.TempDir()
			ctl, err := control.Initialize(filepath.Join(root, "ctl"))
			if err != nil {
				t.Fatal(err)
			}
			defer ctl.Close()
			op := registry.Principal{Kind: registry.Operator}
			if err := ctl.MintProject(op, "p", "p"); err != nil {
				t.Fatal(err)
			}
			if err := ctl.BeginArchiveMigration(op, "p", "g"); err != nil {
				t.Fatal(err)
			}
			l, err := budget.Initialize(filepath.Join(root, "ledger"), budget.Policy{LiveCap: 1 << 30}, func() (budget.Sample, error) { return budget.LocalSample(root, 1<<30) })
			if err != nil {
				t.Fatal(err)
			}
			if err := ctl.AttachBudget(l); err != nil {
				t.Fatal(err)
			}
			source := archive.NewMemStore()
			i, err := ingest.Open(filepath.Join(root, "intake"), config.NewAccountant(config.Default()), source)
			if err != nil {
				t.Fatal(err)
			}
			defer i.Close()
			if err := i.SetBudget(l); err != nil {
				t.Fatal(err)
			}
			r := archive.Record{Project: "p", SessionID: "s", MessageID: "m", Text: "original"}
			if err := ctl.WithArchiveTransaction(op, "p", func(tx *control.ArchiveTransaction) error {
				if err := tx.FinishMigration(func(control.ArchiveState) error { return nil }); err != nil {
					return err
				}
				e, err := tx.Reserve(r, nil, false)
				if err != nil {
					return err
				}
				if phase == "reserved" {
					return nil
				}
				if _, err := i.AcceptEnvelope(e); err != nil {
					return err
				}
				if phase == "projected" || phase == "committed" {
					if err := source.PutEnvelope(e); err != nil {
						return err
					}
				}
				stop := errors.New("crash before processing")
				if phase == "committed" {
					if err := tx.Complete(r, func(archive.Envelope) error { return nil }, func() error { return stop }); !errors.Is(err, stop) {
						t.Fatal(err)
					}
				}
				if phase == "cancelled" {
					if err := tx.Cancel(func(control.ArchiveOperation) error { return nil }, func() error { return stop }); !errors.Is(err, stop) {
						t.Fatal(err)
					}
				}
				return nil
			}); err != nil {
				t.Fatal(err)
			}
			for retry := 0; retry < 2; retry++ {
				if err := ctl.WithArchiveTransaction(op, "p", func(tx *control.ArchiveTransaction) error {
					return i.RecoverEnvelope(tx, func(archive.Record) bool { return phase != "revoked" })
				}); err != nil {
					t.Fatal(err)
				}
			}
			state, _, err := ctl.ArchiveState("p")
			if err != nil || state.Pending != nil || len(l.Snapshot().Pending) != 0 {
				t.Fatal(state, err)
			}
			want := int64(1)
			if phase == "reserved" || phase == "cancelled" || phase == "revoked" {
				want = 0
			}
			if state.CommittedOrdinal != want {
				t.Fatal("false source commitment", state)
			}
			records, err := source.Fetch("p")
			if err != nil || int64(len(records)) != want {
				t.Fatal(records, err)
			}
		})
	}
}
