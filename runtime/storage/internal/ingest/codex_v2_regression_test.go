package ingest

import (
	"aifactory.local/storage/internal/archive"
	"aifactory.local/storage/internal/config"
	"aifactory.local/storage/internal/wal"
	"encoding/json"
	"errors"
	"os"
	"path/filepath"
	"testing"
)

func TestCodexV2AcceptedErrorStillCharged(t *testing.T) {
	d := t.TempDir()
	r := archive.Record{Project: "p", MessageID: "m", Text: "x"}
	b, _ := json.Marshal(r)
	c := config.Default()
	c.WALBytes = wal.RecordCost("a", b)
	i, e := Open(d, config.NewAccountant(c), archive.NewMemStore())
	if e != nil {
		t.Fatal(e)
	}
	defer i.Close()
	idx := filepath.Join(d, "committed.idx")
	if e = os.Remove(idx); e != nil {
		t.Fatal(e)
	}
	if e = os.Mkdir(idx, 0700); e != nil {
		t.Fatal(e)
	}
	rc, e := i.Accept("a", r, config.Usage{FreeBytes: 1 << 40})
	if e == nil || rc.Seq != 1 {
		t.Fatalf("expected durable acceptance with index failure: %+v %v", rc, e)
	}
	os.Remove(idx)
	os.WriteFile(idx, nil, 0600)
	before, _ := i.w.Bytes()
	// Re-delivery of the SAME record (same canonical identity, byte-identical payload) under a
	// DIFFERENT opaque key is a benign duplicate no-op even after the durable-error accept (V3-3 /
	// V4): it must not error and must write no new frame. (Before the V4 fix the durable-error
	// path did not record the identity, so this redelivery would have been admitted as new.)
	if rc, e := i.Accept("b", r, config.Usage{FreeBytes: 1 << 40}); e != nil || !rc.Duplicate {
		t.Fatalf("same-identity redelivery after durable error must be a duplicate no-op: %+v %v", rc, e)
	}
	if after, _ := i.w.Bytes(); after != before {
		t.Fatalf("duplicate redelivery appended bytes: before=%d after=%d", before, after)
	}
	// A GENUINELY NEW record (distinct identity) must still be REJECTED by the physical WAL cap
	// after the durable-error accept filled it — the durable bytes are accounted, not freed.
	r2 := archive.Record{Project: "p", MessageID: "m2", Text: "x"}
	if _, e = i.Accept("c", r2, config.Usage{FreeBytes: 1 << 40}); e == nil {
		n, _ := i.w.Bytes()
		t.Fatalf("new record bypassed cap after durable error: bytes=%d cap=%d counter=%d", n, c.WALBytes, i.walBytes)
	}
}
func TestCodexV2ConflictAfterOpenCompact(t *testing.T) {
	d := t.TempDir()
	c := config.NewAccountant(config.Default())
	s := archive.NewMemStore()
	i, e := Open(d, c, s)
	if e != nil {
		t.Fatal(e)
	}
	r := archive.Record{Project: "p", Text: "a"}
	i.Accept("key", r, config.Usage{FreeBytes: 1 << 40})
	i.Close()
	i, e = Open(d, c, s)
	if e != nil {
		t.Fatal(e)
	}
	defer i.Close()
	i.Compact(func(archive.Record) bool { return true })
	r.Text = "b"
	_, e = i.Accept("key", r, config.Usage{FreeBytes: 1 << 40})
	if !errors.Is(e, wal.ErrKeyConflict) {
		t.Fatalf("lost content hash after open/compact: %v", e)
	}
}
func TestCodexV2ClampCrashBoundaries(t *testing.T) {
	for _, phase := range []string{"before-clamp", "after-clamp", "after-flip"} {
		t.Run(phase, func(t *testing.T) {
			d := t.TempDir()
			s := archive.NewMemStore()
			c := config.NewAccountant(config.Default())
			i, e := Open(d, c, s)
			if e != nil {
				t.Fatal(e)
			}
			u := config.Usage{FreeBytes: 1 << 40}
			i.Accept("a", archive.Record{Project: "a", MessageID: "a"}, u)
			i.Accept("b", archive.Record{Project: "b", MessageID: "b"}, u)
			i.Drain()
			orig := writeWatermark
			if phase != "after-flip" {
				writeWatermark = func(p string, n uint64) error {
					if phase == "after-clamp" {
						if e := orig(p, n); e != nil {
							t.Fatal(e)
						}
					}
					panic("simulated crash")
				}
			}
			func() {
				defer func() { recover() }()
				if _, e = i.Compact(func(r archive.Record) bool { return r.Project != "b" }); e != nil {
					t.Fatal(e)
				}
			}()
			writeWatermark = orig
			i.Close()
			i, e = Open(d, c, s)
			if e != nil {
				t.Fatal(e)
			}
			defer i.Close()
			if _, e = i.DrainGated(func(r archive.Record) bool { return r.Project != "b" }); e != nil {
				t.Fatal(e)
			}
			if _, e = i.Accept("c", archive.Record{Project: "a", MessageID: "c"}, u); e != nil {
				t.Fatal(e)
			}
			if n, e := i.Drain(); e != nil || n != 1 {
				t.Fatalf("new seq skipped after %s: %d %v", phase, n, e)
			}
		})
	}
}
func TestCodexV2PreexistingCorruptCheckpointNotMasked(t *testing.T) {
	d := t.TempDir()
	s := archive.NewMemStore()
	i, e := Open(d, config.NewAccountant(config.Default()), s)
	if e != nil {
		t.Fatal(e)
	}
	defer i.Close()
	i.Accept("a", archive.Record{Project: "p"}, config.Usage{FreeBytes: 1 << 40})
	if e = writeWatermark(i.wmPath, 5); e != nil {
		t.Fatal(e)
	}
	i.committed = 5
	if _, e = i.Compact(func(archive.Record) bool { return true }); e == nil {
		t.Fatal("compaction silently lowered preexisting corrupt checkpoint instead of refusing")
	}
}
