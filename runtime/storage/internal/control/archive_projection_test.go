package control_test

import (
	"aifactory.local/storage/internal/control"
	"aifactory.local/storage/internal/registry"
	"aifactory.local/storage/internal/search"
	"errors"
	"testing"
)

func TestArchiveProjectionReceiptSurvivesRestartAndRequiresProof(t *testing.T) {
	dir := t.TempDir()
	d, err := control.Initialize(dir)
	if err != nil {
		t.Fatal(err)
	}
	op := registry.Principal{Kind: registry.Operator}
	if err := d.MintProject(op, "p", "p"); err != nil {
		t.Fatal(err)
	}
	if err := d.BeginArchiveMigration(op, "p", "source"); err != nil {
		t.Fatal(err)
	}
	attachArchiveLedger(t, d, dir)
	plan := control.ArchiveProjection{Action: "rebuild", Desired: search.Checkpoint{Project: "p", SourceGeneration: "source", ProjectionGeneration: "random-token", PolicyRevision: "0"}}
	if err := d.WithArchiveTransaction(op, "p", func(tx *control.ArchiveTransaction) error {
		if err := tx.ReserveProjection(plan, 1024); err != nil {
			return err
		}
		other := plan
		other.Desired.ProjectionGeneration = "other"
		if err := tx.ReserveProjection(other, 1024); err == nil {
			t.Fatal("pending projection replaced")
		}
		denied := errors.New("not verified")
		if err := tx.FinishProjection(plan, func() error { return denied }); !errors.Is(err, denied) {
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
		got, err := tx.RecoveryProjection()
		if err != nil || got == nil || *got != plan {
			t.Fatal(got, err)
		}
		got.Desired.ProjectionGeneration = "mutated"
		got, err = tx.RecoveryProjection()
		if err != nil || *got != plan {
			t.Fatal("aliased receipt", got, err)
		}
		if err := tx.ReserveProjection(plan, 1024); err != nil {
			return err
		}
		if err := tx.FinishProjection(plan, func() error { return nil }); err != nil {
			return err
		}
		if got, err := tx.RecoveryProjection(); err != nil || got != nil {
			t.Fatal("finished receipt pending", got, err)
		}
		return nil
	}); err != nil {
		t.Fatal(err)
	}
}
