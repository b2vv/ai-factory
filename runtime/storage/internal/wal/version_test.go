package wal

import (
	"bytes"
	"encoding/binary"
	"encoding/hex"
	"errors"
	"hash/crc32"
	"os"
	"path/filepath"
	"testing"
)

func TestVersionedFramesPreserveMixedJournalThroughCompaction(t *testing.T) {
	dir := t.TempDir()
	w, e := Open(dir)
	if e != nil {
		t.Fatal(e)
	}
	if _, e = w.Accept("old", []byte("legacy")); e != nil {
		t.Fatal(e)
	}
	if _, e = w.AcceptV2("new", []byte("metadata-envelope")); e != nil {
		t.Fatal(e)
	}
	if rc, e := w.AcceptV2("new", []byte("metadata-envelope")); e != nil || !rc.Duplicate {
		t.Fatal(rc, e)
	}
	if e = w.Close(); e != nil {
		t.Fatal(e)
	}
	check := func() {
		rs, rep, e := Accepted(dir)
		if e != nil || rep.IsBlocked() || len(rs) != 2 {
			t.Fatal(e, rep, len(rs))
		}
		if rs[0].Version != 1 || rs[1].Version != 2 || string(rs[0].Payload) != "legacy" || string(rs[1].Payload) != "metadata-envelope" {
			t.Fatalf("lost format/payload %+v", rs)
		}
	}
	check()
	if _, e := Compact(dir, func(string, []byte) bool { return true }); e != nil {
		t.Fatal(e)
	}
	check()
	w, e = Open(dir)
	if e != nil {
		t.Fatal(e)
	}
	defer w.Close()
	rc, e := w.AcceptV2("new", []byte("metadata-envelope"))
	if e != nil || !rc.Duplicate {
		t.Fatal(rc, e)
	}
}

func TestV2MagicCorruptionBlocksInsteadOfDowngrading(t *testing.T) {
	dir := t.TempDir()
	w, e := Open(dir)
	if e != nil {
		t.Fatal(e)
	}
	if _, e = w.AcceptV2("new", []byte("metadata")); e != nil {
		t.Fatal(e)
	}
	w.Close()
	data, e := os.ReadFile(filepath.Join(dir, "data"))
	if e != nil {
		t.Fatal(e)
	}
	if data[0] != 'G' {
		t.Fatal("not v2")
	}
	data[0] = 'F'
	if e = os.WriteFile(filepath.Join(dir, "data"), data, 0600); e != nil {
		t.Fatal(e)
	}
	rep, e := RecoverPlan(dir)
	if e != nil {
		t.Fatal(e)
	}
	if !rep.IsBlocked() {
		t.Fatal("magic downgrade accepted")
	}
}

func TestV1WireBytesAndV2BoundedScan(t *testing.T) {
	const golden = "46000000000000000100000001000000016b78d9f73a6c"
	if hex.EncodeToString(frameBytes(1, []byte("k"), []byte("x"))) != golden {
		t.Fatal("v1 bytes changed")
	}
	dir := t.TempDir()
	w, e := Open(dir)
	if e != nil {
		t.Fatal(e)
	}
	defer w.Close()
	if _, e = w.Accept("old", []byte("old")); e != nil {
		t.Fatal(e)
	}
	if _, e = w.AcceptV2("new", []byte("new")); e != nil {
		t.Fatal(e)
	}
	scanner, e := NewScanner(dir, 1<<20)
	if e != nil {
		t.Fatal(e)
	}
	for n := 1; n <= 2; n++ {
		rows, done, e := scanner.Next(1, 1024)
		if e != nil || len(rows) != 1 || rows[0].Version != uint8(n) || done != (n == 2) {
			t.Fatal(rows, done, e)
		}
	}
}

func TestV2AmbiguousCrashPreservesAndBlocks(t *testing.T) {
	for _, fault := range []string{"missing-accept", "short-frame", "unknown-magic"} {
		t.Run(fault, func(t *testing.T) {
			dir := t.TempDir()
			w, e := Open(dir)
			if e != nil {
				t.Fatal(e)
			}
			if _, e = w.AcceptV2("new", []byte("metadata")); e != nil {
				t.Fatal(e)
			}
			w.Close()
			dataPath := filepath.Join(dir, "data")
			data, e := os.ReadFile(dataPath)
			if e != nil {
				t.Fatal(e)
			}
			switch fault {
			case "missing-accept":
				if e = os.Truncate(filepath.Join(dir, "accepts"), 0); e != nil {
					t.Fatal(e)
				}
			case "short-frame":
				data = data[:len(data)-1]
				if e = os.WriteFile(dataPath, data, 0600); e != nil {
					t.Fatal(e)
				}
			case "unknown-magic":
				data[0] = 'Z'
				if e = os.WriteFile(dataPath, data, 0600); e != nil {
					t.Fatal(e)
				}
			}
			rep, e := RecoverPlan(dir)
			if e != nil || !rep.IsBlocked() {
				t.Fatal(rep, e)
			}
			after, e := os.ReadFile(dataPath)
			if e != nil || !bytes.Equal(after, data) {
				t.Fatal("recovery changed accepted bytes", e)
			}
			w, e = Open(dir)
			if e != nil {
				return
			}
			defer w.Close()
			if _, e = w.AcceptV2("other", []byte("other")); e == nil {
				t.Fatal("append into ambiguous WAL")
			}
		})
	}
}

func TestCrossVersionRetryRefusesWithoutRewriting(t *testing.T) {
	for _, firstV2 := range []bool{false, true} {
		dir := t.TempDir()
		w, e := Open(dir)
		if e != nil {
			t.Fatal(e)
		}
		if firstV2 {
			_, e = w.AcceptV2("same", []byte("same"))
		} else {
			_, e = w.Accept("same", []byte("same"))
		}
		if e != nil {
			t.Fatal(e)
		}
		w.Close()
		w, e = Open(dir)
		if e != nil {
			t.Fatal(e)
		}
		if firstV2 {
			_, e = w.Accept("same", []byte("same"))
		} else {
			_, e = w.AcceptV2("same", []byte("same"))
		}
		if e == nil {
			t.Fatal("cross-version duplicate silently accepted")
		}
		w.Close()
		rs, rep, e := Accepted(dir)
		if e != nil || rep.IsBlocked() || len(rs) != 1 {
			t.Fatal(rs, rep, e)
		}
	}
}

func TestCrossVersionRetryAfterCompaction(t *testing.T) {
	dir := t.TempDir()
	w, e := Open(dir)
	if e != nil {
		t.Fatal(e)
	}
	if _, e = w.AcceptV2("k", []byte("p")); e != nil {
		t.Fatal(e)
	}
	w.Close()
	if _, e = Compact(dir, func(string, []byte) bool { return true }); e != nil {
		t.Fatal(e)
	}
	w, e = Open(dir)
	if e != nil {
		t.Fatal(e)
	}
	defer w.Close()
	if _, e = w.Accept("k", []byte("p")); !errors.Is(e, ErrVersionConflict) {
		t.Fatalf("expected format conflict, got %v", e)
	}
	if rc, e := w.AcceptV2("k", []byte("p")); e != nil || !rc.Duplicate {
		t.Fatal(rc, e)
	}
}

func TestUnknownFrameVersionWithValidChecksumsIsBlocked(t *testing.T) {
	dir := t.TempDir()
	w, e := Open(dir)
	if e != nil {
		t.Fatal(e)
	}
	if _, e = w.AcceptV2("new", []byte("metadata")); e != nil {
		t.Fatal(e)
	}
	w.Close()
	data, e := os.ReadFile(filepath.Join(dir, "data"))
	if e != nil {
		t.Fatal(e)
	}
	data[0] = 'Z'
	checksum := crc32.ChecksumIEEE(data[:len(data)-4])
	binary.BigEndian.PutUint32(data[len(data)-4:], checksum)
	if e = os.WriteFile(filepath.Join(dir, "data"), data, 0600); e != nil {
		t.Fatal(e)
	}
	if e = os.WriteFile(filepath.Join(dir, "intents"), intentBytes(1, 0, uint64(len(data)), checksum), 0600); e != nil {
		t.Fatal(e)
	}
	kh := crc32.ChecksumIEEE([]byte("new"))
	chain := acceptChain(0, 1, 0, checksum, kh)
	if e = os.WriteFile(filepath.Join(dir, "accepts"), acceptBytes(1, 0, checksum, kh, chain), 0600); e != nil {
		t.Fatal(e)
	}
	rep, e := RecoverPlan(dir)
	if e != nil || !rep.IsBlocked() {
		t.Fatal("unsupported version accepted", rep, e)
	}
}

func TestApplyRetainsFrameVersion(t *testing.T) {
	dir := t.TempDir()
	w, e := Open(dir)
	if e != nil {
		t.Fatal(e)
	}
	defer w.Close()
	if _, e = w.AcceptV2("v2", []byte("content")); e != nil {
		t.Fatal(e)
	}
	rep, e := RecoverPlan(dir)
	if e != nil {
		t.Fatal(e)
	}
	if _, e = w.Apply(rep); e != nil {
		t.Fatal(e)
	}
	if _, e = w.Accept("v2", []byte("content")); !errors.Is(e, ErrVersionConflict) {
		t.Fatal("Apply lost version", e)
	}
	if rc, e := w.AcceptV2("v2", []byte("content")); e != nil || !rc.Duplicate {
		t.Fatal(rc, e)
	}
}
