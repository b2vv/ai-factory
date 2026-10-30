package wal

import (
	"errors"
	"os"
	"path/filepath"
	"testing"
)

var errInjectedDirSync = errors.New("injected directory-sync failure")

// TestOpenPropagatesDirSyncFailure covers C: a newly created journal's directory entry is
// made durable by fsync'ing the parent directory, and a failure of that fsync must be
// PROPAGATED (not swallowed). This uses deterministic fault injection via the syncDir seam;
// it exercises failure propagation and is explicitly NOT physical power-loss verification,
// which these in-process tests cannot perform.
func TestOpenPropagatesDirSyncFailure(t *testing.T) {
	orig := syncDir
	t.Cleanup(func() { syncDir = orig })
	syncDir = func(string) error { return errInjectedDirSync }

	if _, err := Open(t.TempDir()); err == nil {
		t.Fatalf("Open must propagate a directory-fsync failure, got nil")
	} else if !errors.Is(err, errInjectedDirSync) {
		t.Fatalf("expected the injected dir-sync failure to propagate, got %v", err)
	}
}

// TestOpenCreatesCommittedIndexEagerly confirms C's companion change: committed.idx is
// created during Open so its directory entry is covered by the single directory fsync
// (appendCommitted then only appends to an existing inode).
func TestOpenCreatesCommittedIndexEagerly(t *testing.T) {
	dir := t.TempDir()
	w, err := Open(dir)
	if err != nil {
		t.Fatalf("Open: %v", err)
	}
	defer w.Close()
	if _, err := os.Stat(filepath.Join(dir, "committed.idx")); err != nil {
		t.Fatalf("committed.idx must exist after Open so its directory entry is durable: %v", err)
	}
}
