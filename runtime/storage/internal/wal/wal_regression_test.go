package wal

// Regression tests for the three interim-review WAL findings (IR1, IR2, IR3).
// Each test reproduces the reviewer's evidence from an isolated temp dir using only
// the public WAL API plus byte-level corruption of the on-disk files, and asserts the
// v4-required safe behavior: accepted data is never silently discarded, a clean
// restart keeps the acceptance chain valid, and distinct idempotency keys are never
// collapsed by a hash collision.

import (
	"encoding/binary"
	"hash/crc32"
	"os"
	"path/filepath"
	"testing"
)

// Complementary correctness guard (not one of the six findings): recovery must NOT
// silently truncate a region it cannot prove was unaccepted. A reserved-but-physically-
// short trailing frame with no accept marker (the "interrupted append" shape) is
// INDISTINGUISHABLE from an accepted frame whose data was later truncated and whose
// marker was removed (SF1) — both leave the same bytes on disk. The v4 contract is
// therefore preserve-and-BLOCK, never truncate; the records accepted before it must
// stay intact and remain replayable, and no append is allowed until an operator
// resolves the ambiguity. (This replaces the earlier guard, which asserted an
// unjustified oracle: its setup knew the append was interrupted, but recovery cannot.)
func TestWAL_AmbiguousShortTailIsPreservedNotTruncated(t *testing.T) {
	dir := t.TempDir()
	w, err := Open(dir)
	if err != nil {
		t.Fatal(err)
	}
	if _, err := w.Accept("a", []byte("alpha")); err != nil {
		t.Fatal(err)
	}
	if _, err := w.Accept("b", []byte("bravo")); err != nil {
		t.Fatal(err)
	}
	if err := w.Close(); err != nil {
		t.Fatal(err)
	}

	// Simulate a crash mid-append of a third record: reservation fsynced, frame only
	// half-written, no accept entry — the classic interrupted-append shape.
	dataPath := filepath.Join(dir, "data")
	data, err := os.ReadFile(dataPath)
	if err != nil {
		t.Fatal(err)
	}
	off3 := uint64(len(data))
	fc := frameBytes(3, []byte("c"), []byte("charlie"))
	crc := crc32.Checksum(fc[1:len(fc)-4], crcTab)

	inf, err := os.OpenFile(filepath.Join(dir, "intents"), os.O_WRONLY|os.O_APPEND, 0o600)
	if err != nil {
		t.Fatal(err)
	}
	if _, err := inf.Write(intentBytes(3, off3, uint64(len(fc)), crc)); err != nil {
		t.Fatal(err)
	}
	inf.Close()

	df, err := os.OpenFile(dataPath, os.O_WRONLY|os.O_APPEND, 0o600)
	if err != nil {
		t.Fatal(err)
	}
	if _, err := df.Write(fc[:len(fc)/2]); err != nil { // partial frame
		t.Fatal(err)
	}
	df.Close()

	withPartial, err := os.ReadFile(dataPath)
	if err != nil {
		t.Fatal(err)
	}

	rep, err := RecoverPlan(dir)
	if err != nil {
		t.Fatal(err)
	}
	if !rep.IsBlocked() {
		t.Fatalf("ambiguous short tail must be BLOCKED (indistinguishable from truncated-after-acceptance), got truncateAt=%d", rep.TruncateAt)
	}
	if rep.TruncateAt != -1 {
		t.Fatalf("a blocked report must not propose a data truncation, got TruncateAt=%d", rep.TruncateAt)
	}
	if len(rep.Replay) != 2 {
		t.Fatalf("the two records accepted before the ambiguous tail must still replay, got %d", len(rep.Replay))
	}

	w2, err := Open(dir)
	if err != nil {
		t.Fatal(err)
	}
	defer w2.Close()
	if status, err := w2.Apply(rep); err == nil || status != "BLOCKED" {
		t.Fatalf("Apply on a blocked report must refuse and not mutate; got status=%q err=%v", status, err)
	}
	// Nothing on disk was discarded.
	after, err := os.ReadFile(dataPath)
	if err != nil {
		t.Fatal(err)
	}
	if len(after) != len(withPartial) {
		t.Fatalf("blocked recovery must preserve all bytes: before=%d after=%d", len(withPartial), len(after))
	}
	// Appends are refused until the operator resolves the ambiguity.
	if _, err := w2.Accept("d", []byte("delta")); err == nil {
		t.Fatalf("append must be refused while recovery is BLOCKED")
	}
}

// IR1 — recovery must NOT delete acknowledged data when the accept marker is removed
// and the frame's declared length is corrupted. Reviewer evidence
// (accepted_marker_removed_and_length_corrupt): bytes_before=42, bytes_after=0,
// blocked=false, truncateAt=0 on the buggy tree.
func TestIR1_RecoveryMustNotDiscardAcknowledgedData(t *testing.T) {
	dir := t.TempDir()
	w, err := Open(dir)
	if err != nil {
		t.Fatal(err)
	}
	if _, err := w.Accept("record-1", []byte("payload")); err != nil {
		t.Fatal(err)
	}
	if err := w.Close(); err != nil {
		t.Fatal(err)
	}

	dataPath := filepath.Join(dir, "data")
	acceptsPath := filepath.Join(dir, "accepts")

	before, err := os.ReadFile(dataPath)
	if err != nil {
		t.Fatal(err)
	}
	if len(before) == 0 {
		t.Fatalf("expected a durable frame on disk")
	}

	// Remove the final accept marker (reviewer: "remove the final marker").
	if err := os.WriteFile(acceptsPath, []byte{}, 0o600); err != nil {
		t.Fatal(err)
	}
	// Corrupt the frame's declared payload length to be larger (reviewer: "increase
	// its declared payload length"). payLen is the big-endian u32 at data[13:17].
	corrupt := make([]byte, len(before))
	copy(corrupt, before)
	origPayLen := binary.BigEndian.Uint32(corrupt[13:17])
	binary.BigEndian.PutUint32(corrupt[13:17], origPayLen+4096)
	if err := os.WriteFile(dataPath, corrupt, 0o600); err != nil {
		t.Fatal(err)
	}

	rep, err := RecoverPlan(dir)
	if err != nil {
		t.Fatal(err)
	}
	if !rep.IsBlocked() {
		t.Fatalf("IR1: ambiguous accepted-then-damaged region must be BLOCKED, got replay=%v truncateAt=%d blocked=%v",
			rep.Replay, rep.TruncateAt, rep.BlockedDx)
	}

	w2, err := Open(dir)
	if err != nil {
		t.Fatal(err)
	}
	defer w2.Close()
	status, err := w2.Apply(rep)
	if err == nil || status != "BLOCKED" {
		t.Fatalf("IR1: Apply on a blocked report must refuse and not mutate; got status=%q err=%v", status, err)
	}
	after, err := os.ReadFile(dataPath)
	if err != nil {
		t.Fatal(err)
	}
	if len(after) != len(corrupt) {
		t.Fatalf("IR1: acknowledged data was discarded: before=%d after=%d", len(corrupt), len(after))
	}
}

// IR2 — a clean restart followed by an append must keep the acceptance chain valid.
// Reviewer evidence (clean_reopen_append): the second recovery is BLOCKED at offset 27
// on the buggy tree because chainCRC is not restored on reopen.
func TestIR2_CleanRestartThenAppendKeepsChainValid(t *testing.T) {
	dir := t.TempDir()

	w, err := Open(dir)
	if err != nil {
		t.Fatal(err)
	}
	if _, err := w.Accept("first", []byte("one")); err != nil {
		t.Fatal(err)
	}
	if err := w.Close(); err != nil {
		t.Fatal(err)
	}

	// Reopen, recover (must be clean), then append a second record.
	rep1, err := RecoverPlan(dir)
	if err != nil {
		t.Fatal(err)
	}
	if rep1.IsBlocked() {
		t.Fatalf("IR2: first recovery after a clean close must not be blocked: %v", rep1.BlockedDx)
	}
	w2, err := Open(dir)
	if err != nil {
		t.Fatal(err)
	}
	if _, err := w2.Apply(rep1); err != nil {
		t.Fatalf("IR2: applying a clean recovery must succeed: %v", err)
	}
	if _, err := w2.Accept("second", []byte("two")); err != nil {
		t.Fatalf("IR2: append after a clean restart must be allowed: %v", err)
	}
	if err := w2.Close(); err != nil {
		t.Fatal(err)
	}

	// The journal written across a restart must still validate.
	rep2, err := RecoverPlan(dir)
	if err != nil {
		t.Fatal(err)
	}
	if rep2.IsBlocked() {
		t.Fatalf("IR2: append after reopen corrupted the acceptance chain: %v", rep2.BlockedDx)
	}
	if len(rep2.Replay) != 2 {
		t.Fatalf("IR2: expected both records to replay cleanly, got %d: %+v", len(rep2.Replay), rep2.Replay)
	}
}

// IR3 — two DISTINCT idempotency keys that collide under CRC32 must both be accepted;
// the second must not be reported as a duplicate. Reviewer evidence
// (crc32_distinct_key_collision): keys 7440008307ded59d6711be4d and
// 4e26c206cb6e11b4749c06d3 collide at CRC32 3837691967; the buggy tree accepts the
// first (Seq 1) and drops the second as Duplicate=true, Seq 0.
func TestIR3_CRC32CollisionDoesNotDeduplicateDistinctEvents(t *testing.T) {
	const keyA = "7440008307ded59d6711be4d"
	const keyB = "4e26c206cb6e11b4749c06d3"

	// Guard: prove the two distinct keys really do collide under CRC32, so the test
	// is exercising the reported failure mode and not a coincidence.
	ca := crc32.Checksum([]byte(keyA), crc32.IEEETable)
	cb := crc32.Checksum([]byte(keyB), crc32.IEEETable)
	if keyA == keyB || ca != cb {
		t.Fatalf("IR3: test precondition broken; keys must be distinct and CRC32-colliding (a=%d b=%d)", ca, cb)
	}

	dir := t.TempDir()
	w, err := Open(dir)
	if err != nil {
		t.Fatal(err)
	}
	defer w.Close()

	r1, err := w.Accept(keyA, []byte("event-A"))
	if err != nil {
		t.Fatal(err)
	}
	if r1.Duplicate {
		t.Fatalf("IR3: first key must be accepted, not a duplicate")
	}
	r2, err := w.Accept(keyB, []byte("event-B"))
	if err != nil {
		t.Fatal(err)
	}
	if r2.Duplicate {
		t.Fatalf("IR3: distinct colliding key wrongly deduplicated (CRC32 collision treated as identity)")
	}
	if r2.Seq == r1.Seq || r2.Seq == 0 {
		t.Fatalf("IR3: second distinct key must get its own sequence; got r1.Seq=%d r2.Seq=%d", r1.Seq, r2.Seq)
	}
}
