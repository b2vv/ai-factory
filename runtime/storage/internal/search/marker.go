package search

import (
	"bytes"
	"fmt"
	"os"
	"path/filepath"
)

var marker = []byte("derived-archive-index-v1\n")

func Required(state string) (bool, error) {
	b, e := os.ReadFile(filepath.Join(state, "archive-index-required"))
	if os.IsNotExist(e) {
		return false, nil
	}
	if e != nil {
		return false, e
	}
	if !bytes.Equal(b, marker) {
		return false, fmt.Errorf("search: ambiguous index capability marker")
	}
	return true, nil
}

// Persist before indexing any source record. Disabling PG must not make purge
// forget an existing managed index. A partial marker blocks startup, not erasure.
func MarkRequired(state string) error { return MarkRequiredBudgeted(state, nil) }

// MarkRequiredBudgeted admits the exact capability-marker bytes before creating
// the file. Existing valid markers are idempotent and reserve nothing.
func MarkRequiredBudgeted(state string, reserve func(int64) error) error {
	if exists, e := Required(state); e != nil || exists {
		return e
	}
	if reserve != nil {
		if e := reserve(int64(len(marker))); e != nil {
			return e
		}
	}
	f, e := os.OpenFile(filepath.Join(state, "archive-index-required"), os.O_CREATE|os.O_EXCL|os.O_WRONLY, 0600)
	if e != nil {
		return e
	}
	_, e = f.Write(marker)
	if e == nil {
		e = f.Sync()
	}
	closeErr := f.Close()
	if e == nil {
		e = closeErr
	}
	if e != nil {
		return e
	}
	dir, e := os.Open(state)
	if e != nil {
		return e
	}
	defer dir.Close()
	return dir.Sync()
}
