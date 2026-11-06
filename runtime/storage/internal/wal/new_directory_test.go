package wal_test

import (
	"aifactory.local/storage/internal/wal"
	"path/filepath"
	"testing"
)

func TestOpenCreatesMissingNestedJournal(t *testing.T) {
	dir := filepath.Join(t.TempDir(), "new-parent", "journal")
	w, err := wal.Open(dir)
	if err != nil {
		t.Fatal(err)
	}
	receipt, err := w.AcceptV2("key", []byte("payload"))
	if err != nil {
		t.Fatal(err)
	}
	if err := w.Close(); err != nil {
		t.Fatal(err)
	}
	w, err = wal.Open(dir)
	if err != nil {
		t.Fatal(err)
	}
	defer w.Close()
	again, err := w.AcceptV2("key", []byte("payload"))
	if err != nil {
		t.Fatal(err)
	}
	if !again.Duplicate || again.Seq != receipt.Seq {
		t.Fatal("new journal did not durably preserve accepted identity", receipt, again)
	}
}
