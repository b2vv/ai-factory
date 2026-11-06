package control_test

import (
	"aifactory.local/storage/internal/control"
	"aifactory.local/storage/internal/registry"
	"errors"
	"reflect"
	"testing"
	"time"
)

func TestArchivePolicyAndDeletionReplayExactly(t *testing.T) {
	root := t.TempDir()
	d, err := control.Initialize(root)
	if err != nil {
		t.Fatal(err)
	}
	defer func() { d.Close() }()
	op := registry.Principal{Kind: registry.Operator}
	if err := d.MintProject(op, "p", "fixture"); err != nil {
		t.Fatal(err)
	}
	if err := d.BeginArchiveMigration(op, "p", "g"); err != nil {
		t.Fatal(err)
	}
	attachArchiveLedger(t, d, root)
	if _, err := d.SetConsent(op, "p", "synthetic", "capture", true); err != nil {
		t.Fatal(err)
	}
	if _, err := d.DeleteSessionBarrier(op, "p", "s"); err != nil {
		t.Fatal(err)
	}
	if _, err := d.DeleteProjectBarrier(op, "p"); err != nil {
		t.Fatal(err)
	}
	before, _, err := d.ArchiveState("p")
	if err != nil {
		t.Fatal(err)
	}
	consent := d.Registry().ConsentEpoch("p", "synthetic", "capture")
	barriers := d.Retention().Barriers()
	for n := range barriers {
		barriers[n].CreatedAt = time.Time{}
	}
	if len(barriers) != 2 {
		t.Fatal("missing live barriers")
	}
	if err := d.Close(); err != nil {
		t.Fatal(err)
	}
	d, err = control.Open(root)
	if err != nil {
		t.Fatal(err)
	}
	after, _, err := d.ArchiveState("p")
	if err != nil || !reflect.DeepEqual(before, after) {
		t.Fatal("archive policy changed across replay", before, after, err)
	}
	gotConsent := d.Registry().ConsentEpoch("p", "synthetic", "capture")
	if consent.Epoch != gotConsent.Epoch || consent.Enabled != gotConsent.Enabled {
		t.Fatal("consent changed across replay")
	}
	got := d.Retention().Barriers()
	for n := range got {
		got[n].CreatedAt = time.Time{}
	}
	if !reflect.DeepEqual(barriers, got) {
		t.Fatal("durable deletion barriers lost across replay", barriers, got)
	}
}

func TestArchiveProjectRejectsExpiredTransaction(t *testing.T) {
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
	attachArchiveLedger(t, d, root)
	var expired *control.ArchiveTransaction
	if err := d.WithArchiveTransaction(op, "p", func(tx *control.ArchiveTransaction) error {
		expired = tx
		project, err := tx.Project()
		if err == nil && project != "p" {
			t.Fatal(project)
		}
		return err
	}); err != nil {
		t.Fatal(err)
	}
	if pending, err := expired.ProjectionPending(); !errors.Is(err, control.ErrBlocked) || pending {
		t.Fatal("expired transaction exposes projection", pending, err)
	}

	if project, err := expired.Project(); !errors.Is(err, control.ErrBlocked) || project != "" {
		t.Fatal("expired transaction exposes project", project, err)
	}
}
