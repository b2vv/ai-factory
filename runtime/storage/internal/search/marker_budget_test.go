package search

import (
	"errors"
	"os"
	"path/filepath"
	"testing"
)

func TestCapabilityMarkerRefusesBeforeWriteAndDuplicateCostsZero(t *testing.T) {
	dir := t.TempDir()
	calls := 0
	deny := func(cost int64) error {
		calls++
		if cost != int64(len(marker)) {
			t.Fatal("inexact marker cost", cost)
		}
		return errors.New("full")
	}
	if e := MarkRequiredBudgeted(dir, deny); e == nil {
		t.Fatal("marker budget bypassed")
	}
	if _, e := os.Stat(filepath.Join(dir, "archive-index-required")); !os.IsNotExist(e) {
		t.Fatal("refused marker created", e)
	}
	if e := MarkRequired(dir); e != nil {
		t.Fatal(e)
	}
	if e := MarkRequiredBudgeted(dir, deny); e != nil || calls != 1 {
		t.Fatal("duplicate marker charged", calls, e)
	}
}
