package wal

import (
	"bytes"
	"fmt"
	"os"
	"path/filepath"
)

// OpenExisting never initializes missing evidence. Validate every possible
// compaction source BEFORE recovery can remove a sentinel or staged generation.
func OpenExisting(dir string) (*WAL, error) {
	if err := validateExistingLayout(dir); err != nil {
		return nil, err
	}
	return openWAL(dir, true)
}
func regularEvidence(path string) (bool, error) {
	st, err := os.Lstat(path)
	if os.IsNotExist(err) {
		return false, nil
	}
	if err != nil {
		return false, err
	}
	if !st.Mode().IsRegular() {
		return false, fmt.Errorf("wal: nonregular existing evidence")
	}
	return true, nil
}
func validateExistingLayout(dir string) error {
	st, err := os.Lstat(dir)
	if err != nil {
		return err
	}
	if !st.IsDir() {
		return fmt.Errorf("wal: existing directory required")
	}
	staging := filepath.Join(dir, compactStaging)
	if st, err := os.Lstat(staging); err == nil {
		if !st.IsDir() {
			return fmt.Errorf("wal: non-directory staged evidence")
		}
	} else if !os.IsNotExist(err) {
		return err
	}
	committed := false
	if exists, err := regularEvidence(filepath.Join(dir, compactSentinel)); err != nil {
		return err
	} else if exists {
		raw, err := os.ReadFile(filepath.Join(dir, compactSentinel))
		if err != nil {
			return err
		}
		committed = bytes.Equal(raw, sentinelBytes)
	}
	for _, name := range journalFiles {
		live, err := regularEvidence(filepath.Join(dir, name))
		if err != nil {
			return err
		}
		staged, err := regularEvidence(filepath.Join(staging, name))
		if err != nil {
			return err
		}
		if (!committed && !live) || (committed && !live && !staged) {
			return fmt.Errorf("wal: missing existing journal evidence: %s", name)
		}
	}
	return nil
}
