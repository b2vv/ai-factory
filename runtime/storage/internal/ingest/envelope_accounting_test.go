package ingest

import (
	"aifactory.local/storage/internal/archive"
	"aifactory.local/storage/internal/budget"
	"aifactory.local/storage/internal/config"
	"aifactory.local/storage/internal/wal"
	"errors"
	"path/filepath"
	"reflect"
	"testing"
	"time"
)

func TestEnvelopeOrderingAndExactAccounting(t *testing.T) {
	for _, mode := range []string{"accept-order", "process-order", "processed-debt"} {
		t.Run(mode, func(t *testing.T) {
			root := t.TempDir()
			dir := filepath.Join(root, "intake")
			now := time.Date(2026, 11, 5, 0, 0, 0, 0, time.UTC)
			first := archive.Envelope{Version: 2, Record: archive.Record{Project: "p", SessionID: "s", MessageID: "first"}, Metadata: archive.Metadata{Generation: "g", Ordinal: 1, CapturedAt: &now}}
			target := first
			target.Record.MessageID = "target"
			target.Metadata.Ordinal = 2
			// Deliberately construct an interrupted/out-of-order intake, not a normal
			// control transaction sequence. The public intake must still refuse skipping.
			w, err := wal.Open(dir)
			if err != nil {
				t.Fatal(err)
			}
			if mode != "processed-debt" {
				raw, _ := archive.EncodeEnvelope(first)
				if _, err := w.AcceptV2(archive.IdentityKey(first.Record), raw); err != nil {
					t.Fatal(err)
				}
			}
			if mode == "process-order" {
				raw, _ := archive.EncodeEnvelope(target)
				if _, err := w.AcceptV2(archive.IdentityKey(target.Record), raw); err != nil {
					t.Fatal(err)
				}
			}
			if err := w.Close(); err != nil {
				t.Fatal(err)
			}
			i, err := Open(dir, config.NewAccountant(config.Default()), archive.NewMemStore())
			if err != nil {
				t.Fatal(err)
			}
			defer i.Close()
			l, err := budget.Initialize(filepath.Join(root, "ledger"), budget.Policy{LiveCap: 1 << 30}, func() (budget.Sample, error) { return budget.LocalSample(root, 1<<30) })
			if err != nil {
				t.Fatal(err)
			}
			if err := i.SetBudget(l); err != nil {
				t.Fatal(err)
			}
			raw, _ := archive.EncodeEnvelope(target)
			key := archive.IdentityKey(target.Record)
			if err := l.Reserve(intent("archive-source-v2", key, raw), 1<<20); err != nil {
				t.Fatal(err)
			}
			if mode == "processed-debt" {
				receipt, err := i.AcceptEnvelope(target)
				if err != nil {
					t.Fatal(err)
				}
				if i.acctInvalid {
					t.Fatal("successful physical measurement marked invalid")
				}
				debt, err := archive.EnvelopeReservationBytes(target)
				if err != nil {
					t.Fatal(err)
				}
				if i.pendingArchiveBytes != debt || i.pendingArchive[key] != debt {
					t.Fatal("accepted source debt incorrect")
				}
				reserved := i.reservationTotal
				if err := i.MarkEnvelopeProcessed(target); err != nil {
					t.Fatal(err)
				}
				if i.pendingArchiveBytes != 0 || len(i.pendingArchive) != 0 || i.reservationTotal != reserved+debt || i.committed != receipt.Seq {
					t.Fatal("processed debt not transferred exactly once")
				}
				if err := i.MarkEnvelopeProcessed(target); err != nil {
					t.Fatal(err)
				}
				if i.reservationTotal != reserved+debt {
					t.Fatal("duplicate processing double charged")
				}
				return
			}
			before, rep, err := wal.Accepted(dir)
			if err != nil || rep.IsBlocked() {
				t.Fatal(err)
			}
			debt, reserved, accepted, committed := i.pendingArchiveBytes, i.reservationTotal, i.acceptedTotal, i.committed
			liability := l.Snapshot()
			if mode == "accept-order" {
				_, err = i.AcceptEnvelope(target)
			} else {
				err = i.MarkEnvelopeProcessed(target)
			}
			if !errors.Is(err, ErrMetadataTransaction) {
				t.Errorf("skipped earlier unprocessed record: %v", err)
			}
			after, rep, err := wal.Accepted(dir)
			if err != nil || rep.IsBlocked() || !reflect.DeepEqual(before, after) || !reflect.DeepEqual(liability.Pending, l.Snapshot().Pending) {
				t.Fatal("ordering refusal changed durable evidence", err)
			}
			if debt != i.pendingArchiveBytes || reserved != i.reservationTotal || accepted != i.acceptedTotal || committed != i.committed {
				t.Fatal("ordering refusal changed accounting/watermark")
			}
		})
	}
}

func TestMalformedV2CannotRebuildIdentity(t *testing.T) {
	for _, version := range []int{1, 2} {
		t.Run(string(rune('0'+version)), func(t *testing.T) {
			dir := t.TempDir()
			w, err := wal.Open(dir)
			if err != nil {
				t.Fatal(err)
			}
			if version == 2 {
				_, err = w.AcceptV2("key", []byte("malformed"))
			} else {
				_, err = w.Accept("key", []byte("malformed"))
			}
			if err != nil {
				t.Fatal(err)
			}
			if err := w.Close(); err != nil {
				t.Fatal(err)
			}
			i, err := Open(dir, config.NewAccountant(config.Default()), archive.NewMemStore())
			if i != nil {
				defer i.Close()
			}
			if version == 2 && err == nil {
				t.Fatal("malformed v2 admitted")
			}
			if version == 1 && err != nil {
				t.Fatal("legacy malformed payload no longer preserved for quarantine", err)
			}
		})
	}
}
