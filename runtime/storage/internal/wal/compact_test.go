package wal

import (
	"errors"
	"os"
	"path/filepath"
	"testing"
)

var errFault = errors.New("injected fault")

// acceptN opens a WAL in dir, accepts records key_i -> payload_i for i in 1..n, and closes it.
func acceptN(t *testing.T, dir string, n int) {
	t.Helper()
	w, err := Open(dir)
	if err != nil {
		t.Fatalf("open: %v", err)
	}
	for i := 1; i <= n; i++ {
		if _, err := w.Accept(key(i), payload(i)); err != nil {
			t.Fatalf("accept %d: %v", i, err)
		}
	}
	if err := w.Close(); err != nil {
		t.Fatalf("close: %v", err)
	}
}

func key(i int) string     { return "k" + string(rune('0'+i)) }
func payload(i int) []byte { return []byte("payload-" + string(rune('0'+i))) }

// acceptedKeys returns the set of keys currently accepted in the clean journal.
func acceptedKeys(t *testing.T, dir string) map[string]string {
	t.Helper()
	recs, rep, err := Accepted(dir)
	if err != nil {
		t.Fatalf("accepted: %v", err)
	}
	if rep.IsBlocked() {
		t.Fatalf("journal unexpectedly BLOCKED: %+v", rep.BlockedDx)
	}
	out := map[string]string{}
	for _, r := range recs {
		out[r.Key] = string(r.Payload)
	}
	return out
}

// TestCompactDropsSelectedPreservesOthers: compaction physically removes the dropped keys and
// keeps every other record byte-for-byte; the reopened journal is appendable and its dedup
// index reflects exactly the kept keys (dropped keys append as new; kept keys dedup).
func TestCompactDropsSelectedPreservesOthers(t *testing.T) {
	dir := t.TempDir()
	acceptN(t, dir, 4)

	res, err := Compact(dir, func(k string, _ []byte) bool { return k == "k2" || k == "k4" })
	if err != nil {
		t.Fatalf("compact: %v", err)
	}
	if res.Kept != 2 || res.Dropped != 2 {
		t.Fatalf("want kept=2 dropped=2, got %+v", res)
	}
	got := acceptedKeys(t, dir)
	if len(got) != 2 || got["k2"] != "payload-2" || got["k4"] != "payload-4" {
		t.Fatalf("kept set wrong: %v", got)
	}
	if _, ok := got["k1"]; ok {
		t.Fatalf("dropped key k1 still present")
	}

	// Reopen: kept key dedups (no new frame); dropped key is treated as new and appends.
	w, err := Open(dir)
	if err != nil {
		t.Fatalf("reopen: %v", err)
	}
	defer w.Close()
	rk, err := w.Accept("k2", payload(2))
	if err != nil || !rk.Duplicate {
		t.Fatalf("kept key must dedup after compaction: dup=%v err=%v", rk.Duplicate, err)
	}
	rd, err := w.Accept("k1", []byte("re-added"))
	if err != nil || rd.Duplicate {
		t.Fatalf("dropped key must append as new: dup=%v err=%v", rd.Duplicate, err)
	}
}

// TestCompactRefusesBlockedJournal: a journal with an ambiguous (preserve+BLOCK) tail must NOT
// be compacted; Compact refuses and leaves every byte in place.
func TestCompactRefusesBlockedJournal(t *testing.T) {
	dir := t.TempDir()
	acceptN(t, dir, 2)
	// Append a garbage tail to the accepts journal: this makes recovery BLOCKED (not append-ready).
	accPath := filepath.Join(dir, "accepts")
	before, _ := os.ReadFile(accPath)
	f, _ := os.OpenFile(accPath, os.O_WRONLY|os.O_APPEND, 0o600)
	_, _ = f.Write([]byte("GARBAGETAIL!!"))
	f.Close()

	if _, err := Compact(dir, func(string, []byte) bool { return true }); err == nil {
		t.Fatalf("compact must refuse a BLOCKED journal")
	}
	after, _ := os.ReadFile(accPath)
	if len(after) != len(before)+len("GARBAGETAIL!!") {
		t.Fatalf("compact must not mutate a blocked journal (accepts len changed unexpectedly)")
	}
}

// TestCompactCrashBeforeSentinelLeavesOriginal: a crash during the commit sentinel write
// (before it is durable) must leave the ORIGINAL generation fully intact; the staged copy is
// discarded on the next Open.
func TestCompactCrashBeforeSentinelLeavesOriginal(t *testing.T) {
	dir := t.TempDir()
	acceptN(t, dir, 3)
	orig := writeSentinel
	writeSentinel = func(string) error { return errFault }
	_, err := Compact(dir, func(k string, _ []byte) bool { return k == "k1" })
	writeSentinel = orig
	if err == nil {
		t.Fatalf("expected injected sentinel fault")
	}
	// Staging must be gone and the original 3 records intact.
	if _, statErr := os.Stat(filepath.Join(dir, compactStaging)); !os.IsNotExist(statErr) {
		t.Fatalf("staging dir must be discarded after a pre-commit crash")
	}
	got := acceptedKeys(t, dir)
	if len(got) != 3 {
		t.Fatalf("original generation must be intact (want 3), got %v", got)
	}
}

// TestCompactCrashMidInstallResumes: a crash AFTER the sentinel is durable but partway through
// installing the staged files must be finished on the next Open (resumeCompaction), yielding
// the NEW generation. The journal is never consumed half-installed.
func TestCompactCrashMidInstallResumes(t *testing.T) {
	dir := t.TempDir()
	acceptN(t, dir, 4)
	orig := installGeneration
	// Faulty install: rename only the first journal file, then crash.
	installGeneration = func(d string) error {
		staging := filepath.Join(d, compactStaging)
		_ = os.Rename(filepath.Join(staging, "data"), filepath.Join(d, "data"))
		return errFault
	}
	_, err := Compact(dir, func(k string, _ []byte) bool { return k == "k1" || k == "k3" })
	installGeneration = orig
	if err == nil {
		t.Fatalf("expected injected mid-install fault")
	}
	// Sentinel is durable and staging still holds the un-renamed files: Open must converge.
	if _, statErr := os.Stat(filepath.Join(dir, compactSentinel)); statErr != nil {
		t.Fatalf("sentinel must survive a mid-install crash: %v", statErr)
	}
	w, err := Open(dir)
	if err != nil {
		t.Fatalf("reopen after mid-install crash: %v", err)
	}
	defer w.Close()
	final := acceptedKeys(t, dir)
	if len(final) != 2 || final["k1"] != "payload-1" || final["k3"] != "payload-3" {
		t.Fatalf("resume must install the NEW generation (k1,k3), got %v", final)
	}
	if _, statErr := os.Stat(filepath.Join(dir, compactSentinel)); !os.IsNotExist(statErr) {
		t.Fatalf("sentinel must be cleared after resume")
	}
}

// TestCompactTornSentinelDiscardsStaging: a partially written (torn) sentinel is NOT a durable
// commit; Open must discard the staged generation and keep the original.
func TestCompactTornSentinelDiscardsStaging(t *testing.T) {
	dir := t.TempDir()
	acceptN(t, dir, 3)
	orig := writeSentinel
	// Write a TORN sentinel (one byte short) then fail, simulating a crash mid-sentinel.
	writeSentinel = func(d string) error {
		p := filepath.Join(d, compactSentinel)
		_ = os.WriteFile(p, sentinelBytes[:len(sentinelBytes)-1], 0o600)
		return errFault
	}
	_, err := Compact(dir, func(k string, _ []byte) bool { return k == "k1" })
	writeSentinel = orig
	if err == nil {
		t.Fatalf("expected injected torn-sentinel fault")
	}
	w, err := Open(dir)
	if err != nil {
		t.Fatalf("reopen: %v", err)
	}
	defer w.Close()
	got := acceptedKeys(t, dir)
	if len(got) != 3 {
		t.Fatalf("torn sentinel must discard staging and keep original 3, got %v", got)
	}
	if _, statErr := os.Stat(filepath.Join(dir, compactSentinel)); !os.IsNotExist(statErr) {
		t.Fatalf("torn sentinel must be removed on resume")
	}
}

// TestCompactToEmptyIsValidJournal: purging the only project drops all records, leaving a valid
// EMPTY (not removed) journal that is appendable again.
func TestCompactToEmptyIsValidJournal(t *testing.T) {
	dir := t.TempDir()
	acceptN(t, dir, 2)
	res, err := Compact(dir, func(string, []byte) bool { return false })
	if err != nil {
		t.Fatalf("compact: %v", err)
	}
	if res.Dropped != 2 || res.Kept != 0 {
		t.Fatalf("want all dropped, got %+v", res)
	}
	for _, name := range journalFiles {
		if _, statErr := os.Stat(filepath.Join(dir, name)); statErr != nil {
			t.Fatalf("journal file %q must still exist (never remove the WAL whole): %v", name, statErr)
		}
	}
	w, err := Open(dir)
	if err != nil {
		t.Fatalf("reopen empty: %v", err)
	}
	defer w.Close()
	if _, err := w.Accept("fresh", []byte("x")); err != nil {
		t.Fatalf("empty compacted journal must be appendable: %v", err)
	}
}
