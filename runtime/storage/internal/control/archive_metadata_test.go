package control_test

import (
	"aifactory.local/storage/internal/control"
	"aifactory.local/storage/internal/registry"
	"testing"
)

func TestArchiveMigrationWitnessSurvivesRestart(t *testing.T) {
	dir := t.TempDir()
	d, err := control.Initialize(dir)
	if err != nil {
		t.Fatal(err)
	}
	op := registry.Principal{ID: "op", Kind: registry.Operator}
	if err := d.MintProject(op, "p", "project"); err != nil {
		t.Fatal(err)
	}
	if err := d.BeginArchiveMigration(op, "p", "source-generation"); err != nil {
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
	got, ok, err := d.ArchiveState("p")
	if err != nil || !ok || got.Version != 2 || got.Generation != "source-generation" || got.MigrationComplete || got.NextOrdinal != 1 || got.CommittedOrdinal != 0 {
		t.Fatal(got, ok, err)
	}
	if err := d.BeginArchiveMigration(op, "p", "source-generation"); err != nil {
		t.Fatal("retry", err)
	}
	if err := d.BeginArchiveMigration(op, "p", "replacement"); err == nil {
		t.Fatal("generation reset allowed")
	}
	if _, ok, err := d.ArchiveState("other"); err != nil || ok {
		t.Fatal("cross project", ok, err)
	}
}
