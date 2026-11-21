package control_test

import (
	"aifactory.local/storage/internal/archive"
	"aifactory.local/storage/internal/control"
	"aifactory.local/storage/internal/registry"
	"aifactory.local/storage/internal/wal"
	"path/filepath"
	"reflect"
	"strings"
	"testing"
)

func TestSummaryReservationRequiresWitnessAndKeepsMarkerOnRetry(t *testing.T) {
	d, _, op := summaryControl(t)
	defer d.Close()
	if _, e := d.SetConsent(op, "p", "synthetic", "capture", true); e != nil {
		t.Fatal(e)
	}
	r := archive.Record{Project: "p", Provider: "synthetic", SourceInstance: "i", SessionID: "s", MessageID: "af-summary-v1/" + strings.Repeat("a", 64), Type: archive.TypeSummary, Role: "assistant", Text: "synthetic derived payload", ConsentEpoch: 1}
	if e := d.WithArchiveTransaction(op, "p", func(tx *control.ArchiveTransaction) error { _, e := tx.ReserveSummary(r, 1); return e }); e == nil {
		t.Fatal("derived reserve without consent witness")
	}
	if _, e := d.SetConsent(op, "p", "synthetic", "summary", true); e != nil {
		t.Fatal(e)
	}
	if e := d.WithArchiveTransaction(op, "p", func(tx *control.ArchiveTransaction) error {
		first, e := tx.ReserveSummary(r, 1)
		if e != nil {
			return e
		}
		if first.Metadata.DerivedKind != archive.DerivedSessionExtract || first.Metadata.CapturedAt == nil || first.Metadata.Legacy {
			t.Fatal("unmarked derived reservation", first)
		}
		if _, e = tx.Reserve(r, nil, false); e == nil {
			t.Fatal("ordinary reserve converted pending derived source")
		}
		again, e := tx.ReserveSummary(r, 1)
		if e != nil {
			return e
		}
		a, _ := archive.EncodeEnvelope(first)
		b, _ := archive.EncodeEnvelope(again)
		if string(a) != string(b) {
			t.Fatal("retry changed derived envelope")
		}
		return tx.Complete(r, func(archive.Envelope) error { return nil }, func() error { return nil })
	}); e != nil {
		t.Fatal(e)
	}
	if _, e := d.SetConsent(op, "p", "synthetic", "summary", false); e != nil {
		t.Fatal(e)
	}
	r.MessageID = "af-summary-v1/" + strings.Repeat("b", 64)
	if e := d.WithArchiveTransaction(op, "p", func(tx *control.ArchiveTransaction) error { _, e := tx.ReserveSummary(r, 1); return e }); e == nil {
		t.Fatal("revoked derivation reserved")
	}
}

func TestSummaryReservationRejectsMalformedAndStaleAuthorityBeforeReservation(t *testing.T) {
	cases := []struct {
		name   string
		mutate func(*archive.Record)
		setup  func(*control.Durable, registry.Principal) error
		epoch  int64
	}{
		{name: "foreign-project", mutate: func(r *archive.Record) { r.Project = "foreign" }},
		{name: "manual-type", mutate: func(r *archive.Record) { r.Type = archive.TypeMessage }},
		{name: "wrong-role", mutate: func(r *archive.Record) { r.Role = "user" }},
		{name: "sequence", mutate: func(r *archive.Record) { r.Seq = 1 }},
		{name: "parent", mutate: func(r *archive.Record) { r.ParentID = "original" }},
		{name: "edited", mutate: func(r *archive.Record) { r.Edited = true }},
		{name: "withdrawn", mutate: func(r *archive.Record) { r.Withdrawn = true }},
		{name: "missing-namespace", mutate: func(r *archive.Record) { r.MessageID = strings.Repeat("a", 64) }},
		{name: "short-digest", mutate: func(r *archive.Record) { r.MessageID = archive.SessionExtractMessagePrefix + strings.Repeat("a", 62) }},
		{name: "invalid-hex", mutate: func(r *archive.Record) { r.MessageID = archive.SessionExtractMessagePrefix + strings.Repeat("z", 64) }},
		{name: "future-capture-epoch", mutate: func(r *archive.Record) { r.ConsentEpoch = 2 }},
		{name: "zero-capture-epoch", mutate: func(r *archive.Record) { r.ConsentEpoch = 0 }},
		{name: "wrong-summary-epoch", epoch: 2},
		{name: "unknown-provider", mutate: func(r *archive.Record) { r.Provider = "other" }},
		{name: "project-retention", setup: func(d *control.Durable, op registry.Principal) error {
			_, err := d.DeleteProjectBarrier(op, "p")
			return err
		}},
		{name: "session-retention", setup: func(d *control.Durable, op registry.Principal) error {
			_, err := d.DeleteSessionBarrier(op, "p", "s")
			return err
		}},
		{name: "capture-disabled", setup: func(d *control.Durable, op registry.Principal) error {
			_, err := d.SetConsent(op, "p", "synthetic", "capture", false)
			return err
		}},
		{name: "capture-regranted-old-source", setup: func(d *control.Durable, op registry.Principal) error {
			for _, enabled := range []bool{false, true} {
				if _, err := d.SetConsent(op, "p", "synthetic", "capture", enabled); err != nil {
					return err
				}
			}
			return nil
		}},
		{name: "summary-regranted-stale-authority", setup: func(d *control.Durable, op registry.Principal) error {
			for _, enabled := range []bool{false, true} {
				if _, err := d.SetConsent(op, "p", "synthetic", "summary", enabled); err != nil {
					return err
				}
			}
			return nil
		}},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			d, dir, op := summaryControl(t)
			defer d.Close()
			for _, purpose := range []string{"capture", "summary"} {
				if _, err := d.SetConsent(op, "p", "synthetic", purpose, true); err != nil {
					t.Fatal(err)
				}
			}
			if tc.setup != nil {
				if err := tc.setup(d, op); err != nil {
					t.Fatal(err)
				}
			}
			r := archive.Record{Project: "p", Provider: "synthetic", SourceInstance: "i", SessionID: "s", MessageID: archive.SessionExtractMessagePrefix + strings.Repeat("a", 64), Type: archive.TypeSummary, Role: "assistant", Text: "synthetic sealed-body admission fixture", ConsentEpoch: 1}
			if tc.mutate != nil {
				tc.mutate(&r)
			}
			epoch := tc.epoch
			if epoch == 0 {
				epoch = 1
			}
			beforeWAL, report, err := wal.Accepted(filepath.Join(dir, "wal"))
			if err != nil || report.IsBlocked() {
				t.Fatal("baseline WAL unavailable", err)
			}
			before, _, err := d.ArchiveState("p")
			if err != nil {
				t.Fatal(err)
			}
			err = d.WithArchiveTransaction(op, "p", func(tx *control.ArchiveTransaction) error { _, err := tx.ReserveSummary(r, epoch); return err })
			if err == nil {
				t.Fatal("unsupported derived reservation accepted")
			}
			afterWAL, report, walErr := wal.Accepted(filepath.Join(dir, "wal"))
			if walErr != nil || report.IsBlocked() || !reflect.DeepEqual(beforeWAL, afterWAL) {
				t.Fatal("refusal changed retained WAL", walErr)
			}
			after, _, err := d.ArchiveState("p")
			if err != nil || after.Pending != nil || after.NextOrdinal != before.NextOrdinal || after.CommittedOrdinal != before.CommittedOrdinal {
				t.Fatal("refusal changed reservation/frontier", err)
			}
		})
	}
}
