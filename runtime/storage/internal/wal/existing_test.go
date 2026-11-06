package wal_test

import (
	"aifactory.local/storage/internal/wal"
	"os"
	"path/filepath"
	"testing"
)

func TestExistingWALNeverRecreatesLostEvidence(t *testing.T) {
	for _, missing := range []string{"data", "intents", "accepts", "committed.idx"} {
		t.Run(missing, func(t *testing.T) {
			dir := t.TempDir()
			w, err := wal.Open(dir)
			if err != nil {
				t.Fatal(err)
			}
			if _, err := w.AcceptV2("key", []byte("payload")); err != nil {
				t.Fatal(err)
			}
			w.Close()
			if err := os.Remove(filepath.Join(dir, missing)); err != nil {
				t.Fatal(err)
			}
			if w, err := wal.OpenExisting(dir); err == nil {
				w.Close()
				t.Fatal("lost evidence recreated")
			}
			if _, err := os.Stat(filepath.Join(dir, missing)); !os.IsNotExist(err) {
				t.Fatal("missing file recreated", err)
			}
		})
	}
	dir := filepath.Join(t.TempDir(), "absent")
	if w, err := wal.OpenExisting(dir); err == nil {
		w.Close()
		t.Fatal("absent state initialized")
	}
	if _, err := os.Stat(dir); !os.IsNotExist(err) {
		t.Fatal("absent directory created", err)
	}
	good := t.TempDir()
	w, err := wal.Open(good)
	if err != nil {
		t.Fatal(err)
	}
	w.Close()
	w, err = wal.OpenExisting(good)
	if err != nil {
		t.Fatal("valid empty journal refused", err)
	}
	w.Close()
}
