package control_test

import (
	"aifactory.local/storage/internal/archive"
	"aifactory.local/storage/internal/control"
	"aifactory.local/storage/internal/registry"
	"aifactory.local/storage/internal/wal"
	"encoding/json"
	"os"
	"path/filepath"
	"reflect"
	"testing"
)

func TestProjectionExpectedBindingAndDurableWatermark(t *testing.T) {
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
	if err = d.BeginArchiveMigration(op, "p", "source"); err != nil {
		t.Fatal(err)
	}
	attachArchiveLedger(t, d, root)
	record := archive.Record{Project: "p", SessionID: "s", MessageID: "m"}
	if err = d.WithArchiveTransaction(op, "p", func(tx *control.ArchiveTransaction) error {
		if _, err := tx.Reserve(record, nil, true); err != nil {
			return err
		}
		return tx.Complete(record, func(archive.Envelope) error { return nil }, func() error { return nil })
	}); err != nil {
		t.Fatal(err)
	}
	expected := archive.IndexCheckpoint{Project: "p", SourceGeneration: "source", ProjectionGeneration: "index", PolicyRevision: "0"}
	desired := expected
	desired.Ordinal = 1
	desired.Complete = true
	plan := control.ArchiveProjection{Action: "complete", Expected: expected, Desired: desired}
	for name, change := range map[string]func(*archive.IndexCheckpoint){
		"project":             func(c *archive.IndexCheckpoint) { c.Project = "other" },
		"source":              func(c *archive.IndexCheckpoint) { c.SourceGeneration = "other" },
		"projection":          func(c *archive.IndexCheckpoint) { c.ProjectionGeneration = "other" },
		"policy":              func(c *archive.IndexCheckpoint) { c.PolicyRevision = "1" },
		"negative-position":   func(c *archive.IndexCheckpoint) { c.Ordinal = -1 },
		"regressing-position": func(c *archive.IndexCheckpoint) { c.Ordinal = 2 },
	} {
		t.Run(name, func(t *testing.T) {
			bad := plan
			change(&bad.Expected)
			before, _, err := d.ArchiveState("p")
			if err != nil {
				t.Fatal(err)
			}
			budgetBefore := d.Budget().Snapshot()
			err = d.WithArchiveTransaction(op, "p", func(tx *control.ArchiveTransaction) error { return tx.ReserveProjection(bad, 4096) })
			if err == nil {
				t.Fatal("mismatched expected checkpoint admitted")
			}
			after, _, err := d.ArchiveState("p")
			if err != nil || !reflect.DeepEqual(before, after) || !reflect.DeepEqual(budgetBefore, d.Budget().Snapshot()) {
				t.Fatal("rejected binding changed durable state", err)
			}
		})
	}
	watermark := func() uint64 {
		t.Helper()
		raw, err := os.ReadFile(filepath.Join(root, "control.meta"))
		if err != nil {
			t.Fatal(err)
		}
		var meta struct {
			HighWater uint64 `json:"high_water"`
		}
		if err = json.Unmarshal(raw, &meta); err != nil {
			t.Fatal(err)
		}
		records, report, err := wal.Accepted(filepath.Join(root, "wal"))
		if err != nil || report.IsBlocked() {
			t.Fatal(err)
		}
		var latest uint64
		for _, r := range records {
			if r.Seq > latest {
				latest = r.Seq
			}
		}
		if meta.HighWater != latest {
			t.Fatalf("acknowledged authority watermark %d differs from durable receipt %d", meta.HighWater, latest)
		}
		return meta.HighWater
	}
	before := watermark()
	apply := func() {
		t.Helper()
		if err := d.WithArchiveTransaction(op, "p", func(tx *control.ArchiveTransaction) error {
			if err := tx.ReserveProjection(plan, 4096); err != nil {
				return err
			}
			return tx.FinishProjection(plan, func() error { return nil })
		}); err != nil {
			t.Fatal(err)
		}
	}
	apply()
	if watermark() <= before {
		t.Fatal("new receipt did not advance watermark")
	}
	if err = d.MintProject(op, "other", "unrelated authority receipt"); err != nil {
		t.Fatal(err)
	}
	advanced := watermark()
	apply()
	if watermark() != advanced {
		t.Fatal("retry regressed or invented authority position")
	}
}
