package wal

import (
	"errors"
	"os"
	"path/filepath"
	"testing"
)

func TestCompactionPeakExactFitAndOneByteShort(t *testing.T) {
	dir := t.TempDir()
	w, e := Open(dir)
	if e != nil {
		t.Fatal(e)
	}
	for _, key := range []string{"drop", "keep"} {
		if _, e = w.Accept(key, []byte("payload")); e != nil {
			t.Fatal(e)
		}
	}
	w.Close()
	recs, _, e := Accepted(dir)
	if e != nil {
		t.Fatal(e)
	}
	keep := func(k string, _ []byte) bool { return k == "keep" }
	p, e := PlanCompaction(dir, recs, keep, MaintenanceBudget{1 << 20, 1 << 20}, 0)
	if e != nil {
		t.Fatal(e)
	}
	before, _ := os.ReadFile(filepath.Join(dir, "data"))
	if _, e = CompactWithin(dir, keep, MaintenanceBudget{1 << 20, p.PeakBytes - 1}); !errors.Is(e, ErrMaintenanceBudget) {
		t.Fatal("over-budget transition", e)
	}
	after, _ := os.ReadFile(filepath.Join(dir, "data"))
	if string(before) != string(after) {
		t.Fatal("rejected transition changed journal")
	}
	if _, e = os.Stat(filepath.Join(dir, compactStaging)); !os.IsNotExist(e) {
		t.Fatal("staging created before reservation", e)
	}
	oldInstall := installGeneration
	defer func() { installGeneration = oldInstall }()
	installGeneration = func(d string) error {
		actual, e := ManagedBytes(d)
		if e != nil {
			return e
		}
		if actual != p.PeakBytes {
			t.Fatalf("peak actual=%d planned=%d", actual, p.PeakBytes)
		}
		return oldInstall(d)
	}
	result, e := CompactWithin(dir, keep, MaintenanceBudget{1 << 20, p.PeakBytes})
	if e != nil || result.Dropped != 1 {
		t.Fatal(result, e)
	}
	w, e = Open(dir)
	if e != nil {
		t.Fatal(e)
	}
	defer w.Close()
	if !w.Has("keep") || w.Has("drop") {
		t.Fatal("wrong generation")
	}
}
func TestBoundedScanContinuationChangeAndCorruption(t *testing.T) {
	dir := t.TempDir()
	w, e := Open(dir)
	if e != nil {
		t.Fatal(e)
	}
	defer w.Close()
	for _, k := range []string{"a", "b", "c"} {
		if _, e = w.Accept(k, []byte("payload")); e != nil {
			t.Fatal(e)
		}
	}
	s, e := NewScanner(dir, 1<<20)
	if e != nil {
		t.Fatal(e)
	}
	for n, k := range []string{"a", "b", "c"} {
		rows, done, e := s.Next(1, 256)
		if e != nil || len(rows) != 1 || rows[0].Key != k || done != (n == 2) {
			t.Fatal(rows, done, e)
		}
	}
	s, _ = NewScanner(dir, 1<<20)
	if _, _, e = s.Next(1, 1); !errors.Is(e, ErrMaintenanceBudget) {
		t.Fatal(e)
	}
	if _, e = w.Accept("d", []byte("payload")); e != nil {
		t.Fatal(e)
	}
	if rows, done, e := s.Next(1, 256); e != nil || done || len(rows) != 1 || rows[0].Key != "a" {
		t.Fatal("append starved stable prefix", rows, done, e)
	}
	// Replacing the generation invalidates the cursor even when lengths match.
	dataPath := filepath.Join(dir, "data")
	raw, _ := os.ReadFile(dataPath)
	os.WriteFile(dataPath+".replace", raw, 0600)
	os.Rename(dataPath+".replace", dataPath)
	if _, _, e = s.Next(1, 256); !errors.Is(e, ErrScanChanged) {
		t.Fatal("replacement reused offsets", e)
	}
	if _, e = NewScanner(dir, 1); !errors.Is(e, ErrMaintenanceBudget) {
		t.Fatal("input cap ignored", e)
	}
	w.Close()
	p := filepath.Join(dir, "accepts")
	b, _ := os.ReadFile(p)
	b[len(b)-1] ^= 1
	os.WriteFile(p, b, 0600)
	s, e = NewScanner(dir, 1<<20)
	if e != nil {
		t.Fatal(e)
	}
	if _, _, e = s.Next(100, 1<<20); e == nil {
		t.Fatal("corrupt chain accepted")
	}
	after, _ := os.ReadFile(p)
	if string(after) != string(b) {
		t.Fatal("scan mutated ambiguous evidence")
	}
}

func TestBudgetedTransitionCrashResumesWithoutNewFormat(t *testing.T) {
	dir := t.TempDir()
	w, e := Open(dir)
	if e != nil {
		t.Fatal(e)
	}
	for _, key := range []string{"drop", "keep"} {
		if _, e = w.Accept(key, []byte("source")); e != nil {
			t.Fatal(e)
		}
	}
	w.Close()
	original := installGeneration
	defer func() { installGeneration = original }()
	installGeneration = func(dir string) error {
		if e := os.Rename(filepath.Join(dir, compactStaging, "data"), filepath.Join(dir, "data")); e != nil {
			return e
		}
		return errors.New("simulated interrupted install")
	}
	if _, e = CompactWithin(dir, func(k string, _ []byte) bool { return k == "keep" }, MaintenanceBudget{1 << 20, 1 << 20}); e == nil {
		t.Fatal("fault not observed")
	}
	installGeneration = original
	// The unchanged legacy Open/sentinel recovery path finishes the transition.
	w, e = Open(dir)
	if e != nil {
		t.Fatal(e)
	}
	defer w.Close()
	rows, rep, e := Accepted(dir)
	if e != nil || rep.IsBlocked() || len(rows) != 1 || rows[0].Key != "keep" {
		t.Fatal(rows, rep, e)
	}
	if _, e = w.Accept("next", []byte("next")); e != nil {
		t.Fatal(e)
	}
}
