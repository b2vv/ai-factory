package search

import (
	"os"
	"path/filepath"
	"testing"
)

func TestIndexCapabilityMarkerSurvivesAndRejectsAmbiguity(t *testing.T) {
	dir := t.TempDir()
	if yes, e := Required(dir); e != nil || yes {
		t.Fatal(yes, e)
	}
	if e := MarkRequired(dir); e != nil {
		t.Fatal(e)
	}
	if e := MarkRequired(dir); e != nil {
		t.Fatal(e)
	}
	if yes, e := Required(dir); e != nil || !yes {
		t.Fatal(yes, e)
	}
	if e := os.WriteFile(filepath.Join(dir, "archive-index-required"), []byte("partial"), 0600); e != nil {
		t.Fatal(e)
	}
	if _, e := Required(dir); e == nil {
		t.Fatal("partial marker accepted")
	}
}
