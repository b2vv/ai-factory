package wal

// Regression tests for the three remaining WAL blockers found by the independent
// sixfix affected-scope review (SF1, SF2, SF3). Each reproduces a reviewer probe
// observation from an isolated temp dir using only the public WAL API plus byte-level
// corruption of the on-disk journal, and asserts the v4 contract: a missing/invalid
// acceptance marker is AMBIGUOUS (never proof of non-acceptance), corrupt journal
// metadata must never panic nor silently become append-ready, and a secondary dedup
// cache must never manufacture an acceptance that the authoritative records contradict.
//
// No silent data loss, no panic, preserve-and-BLOCK when proof of non-acceptance is
// unavailable.

import (
	"bytes"
	"encoding/binary"
	"os"
	"path/filepath"
	"testing"
)

// SF1 — a physically shorter data file plus a missing accept marker is NOT proof the
// frame was never accepted. Reviewer probe accepted_data_physically_truncated_and_
// marker_removed: before=42 bytes, after=0, blocked=false, truncateAt=0 (accepted bytes
// deleted). The v4 contract requires BLOCKED with the bytes preserved.
func TestSF1_PhysicalDataTruncationWithMissingMarkerIsBlocked(t *testing.T) {
	dir := t.TempDir()
	w, err := Open(dir)
	if err != nil {
		t.Fatal(err)
	}
	if _, err := w.Accept("alpha", []byte("synthetic-payload")); err != nil {
		t.Fatal(err)
	}
	if err := w.Close(); err != nil {
		t.Fatal(err)
	}

	dataPath := filepath.Join(dir, "data")
	data, err := os.ReadFile(dataPath)
	if err != nil {
		t.Fatal(err)
	}
	before := len(data)
	// Shorten the accepted frame by one byte and remove its accept marker.
	if err := os.WriteFile(dataPath, data[:before-1], 0o600); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(dir, "accepts"), nil, 0o600); err != nil {
		t.Fatal(err)
	}

	rep, err := RecoverPlan(dir)
	if err != nil {
		t.Fatal(err)
	}
	if !rep.IsBlocked() {
		t.Fatalf("SF1: physically truncated accepted frame with no marker must be BLOCKED, got blocked=false truncateAt=%d", rep.TruncateAt)
	}
	w2, err := Open(dir)
	if err != nil {
		t.Fatal(err)
	}
	defer w2.Close()
	status, err := w2.Apply(rep)
	if err == nil || status != "BLOCKED" {
		t.Fatalf("SF1: Apply on a blocked report must refuse; got status=%q err=%v", status, err)
	}
	after, err := os.ReadFile(dataPath)
	if err != nil {
		t.Fatal(err)
	}
	if len(after) != before-1 {
		t.Fatalf("SF1: ambiguous bytes must be preserved, not discarded: before=%d after=%d", before-1, len(after))
	}
}

// SF1 variant — enlarging the reservation's recorded frame length (and removing the
// marker) must not let recovery truncate the still-present accepted bytes. Reviewer
// probe accepted_intent_length_damaged_and_marker_removed: before=43, after=0.
func TestSF1_IntentLengthEnlargedWithMissingMarkerIsBlocked(t *testing.T) {
	dir := t.TempDir()
	w, err := Open(dir)
	if err != nil {
		t.Fatal(err)
	}
	if _, err := w.Accept("alpha", []byte("synthetic-payload")); err != nil {
		t.Fatal(err)
	}
	if err := w.Close(); err != nil {
		t.Fatal(err)
	}

	dataPath := filepath.Join(dir, "data")
	before, err := os.ReadFile(dataPath)
	if err != nil {
		t.Fatal(err)
	}
	// Enlarge the recorded frame length in the first reservation (frameLen u64 at [17:25]).
	intentsPath := filepath.Join(dir, "intents")
	ib, err := os.ReadFile(intentsPath)
	if err != nil {
		t.Fatal(err)
	}
	binary.BigEndian.PutUint64(ib[17:25], 9999)
	if err := os.WriteFile(intentsPath, ib, 0o600); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(dir, "accepts"), nil, 0o600); err != nil {
		t.Fatal(err)
	}

	rep, err := RecoverPlan(dir)
	if err != nil {
		t.Fatal(err)
	}
	if !rep.IsBlocked() {
		t.Fatalf("SF1: damaged reservation length with no marker must be BLOCKED, got truncateAt=%d", rep.TruncateAt)
	}
	after, err := os.ReadFile(dataPath)
	if err != nil {
		t.Fatal(err)
	}
	if len(after) != len(before) {
		t.Fatalf("SF1: accepted bytes must be preserved: before=%d after=%d", len(before), len(after))
	}
}

// SF2 — a corrupt reservation offset must not panic; recovery must return a BLOCKED
// diagnostic. Reviewer probe intent_span_overflow: off set to MaxUint64-10 overflowed
// off+frameLen and sliced data[off:spanEnd], panicking.
func TestSF2_CorruptIntentOffsetDoesNotPanicAndBlocks(t *testing.T) {
	dir := t.TempDir()
	w, err := Open(dir)
	if err != nil {
		t.Fatal(err)
	}
	if _, err := w.Accept("alpha", []byte("synthetic-payload")); err != nil {
		t.Fatal(err)
	}
	if err := w.Close(); err != nil {
		t.Fatal(err)
	}

	intentsPath := filepath.Join(dir, "intents")
	ib, err := os.ReadFile(intentsPath)
	if err != nil {
		t.Fatal(err)
	}
	// Corrupt the reservation offset (u64 at [9:17]) to a value that overflows off+len.
	binary.BigEndian.PutUint64(ib[9:17], ^uint64(0)-10)
	if err := os.WriteFile(intentsPath, ib, 0o600); err != nil {
		t.Fatal(err)
	}

	var rep Report
	func() {
		defer func() {
			if p := recover(); p != nil {
				t.Fatalf("SF2: RecoverPlan panicked on a corrupt reservation offset: %v", p)
			}
		}()
		var e error
		rep, e = RecoverPlan(dir)
		if e != nil {
			t.Fatalf("SF2: RecoverPlan returned error: %v", e)
		}
	}()
	if !rep.IsBlocked() {
		t.Fatalf("SF2: corrupt reservation metadata must be BLOCKED, got blocked=false truncateAt=%d", rep.TruncateAt)
	}
}

// SF2 — trailing garbage on the accepts file must not be silently ignored: recovery
// must treat the journal as needing resolution so no NEW acknowledgment is written
// behind the garbage (which would then fail its own recovery). Reviewer probe
// garbage_accept_tail_append: before_blocked=false allowed a second Accept whose next
// recovery was BLOCKED.
func TestSF2_GarbageAcceptTailIsNotAppendReady(t *testing.T) {
	dir := t.TempDir()
	w, err := Open(dir)
	if err != nil {
		t.Fatal(err)
	}
	if _, err := w.Accept("a", []byte("one")); err != nil {
		t.Fatal(err)
	}
	if err := w.Close(); err != nil {
		t.Fatal(err)
	}

	// Append one garbage byte to the accepts file after a clean accepted record.
	f, err := os.OpenFile(filepath.Join(dir, "accepts"), os.O_APPEND|os.O_WRONLY, 0o600)
	if err != nil {
		t.Fatal(err)
	}
	if _, err := f.Write([]byte{0x7f}); err != nil {
		t.Fatal(err)
	}
	f.Close()

	rep, err := RecoverPlan(dir)
	if err != nil {
		t.Fatal(err)
	}
	if !rep.IsBlocked() {
		t.Fatalf("SF2: an unparsed/garbage accepts tail must block recovery (needs resolution), got blocked=false")
	}
	// A journal with an unresolved tail must not accept a new record (no ack behind garbage).
	w2, err := Open(dir)
	if err != nil {
		t.Fatal(err)
	}
	defer w2.Close()
	if _, err := w2.Accept("b", []byte("two")); err == nil {
		t.Fatalf("SF2: Accept must be refused while the journal has an unresolved garbage tail")
	}
}

// SF3 — the persisted exact-key dedup index must not manufacture a duplicate that the
// authoritative journal contradicts. Reviewer probe corrupt_index_invents_duplicate:
// committed.idx key bytes changed to a never-accepted key made Accept(thatKey) return
// Duplicate=true, silently dropping distinct data.
func TestSF3_CorruptIndexDoesNotInventDuplicate(t *testing.T) {
	dir := t.TempDir()
	w, err := Open(dir)
	if err != nil {
		t.Fatal(err)
	}
	if _, err := w.Accept("alpha", []byte("one")); err != nil {
		t.Fatal(err)
	}
	if err := w.Close(); err != nil {
		t.Fatal(err)
	}

	// Corrupt the persisted index: overwrite the same-length key "alpha" with "bravo".
	idxPath := filepath.Join(dir, "committed.idx")
	b, err := os.ReadFile(idxPath)
	if err != nil {
		t.Fatal(err)
	}
	i := bytes.Index(b, []byte("alpha"))
	if i < 0 {
		t.Fatalf("SF3: could not locate the key in committed.idx")
	}
	copy(b[i:], []byte("bravo"))
	if err := os.WriteFile(idxPath, b, 0o600); err != nil {
		t.Fatal(err)
	}

	w2, err := Open(dir)
	if err != nil {
		t.Fatal(err)
	}
	defer w2.Close()
	rc, err := w2.Accept("bravo", []byte("distinct"))
	if err != nil {
		t.Fatal(err)
	}
	if rc.Duplicate {
		t.Fatalf("SF3: a never-accepted key was reported as a duplicate from a corrupt index (Seq=%d); distinct data would be silently dropped", rc.Seq)
	}
}
