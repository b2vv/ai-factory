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

func TestCodexV3ReseedFailureBlocksNextAccept(t *testing.T) {
	d := t.TempDir()
	r := archive.Record{Project: "p", MessageID: "a", Text: "x"}
	b, _ := json.Marshal(r)
	cfg := config.Default()
	cfg.WALBytes = wal.RecordCost("a", b)
	i, e := Open(d, config.NewAccountant(cfg), archive.NewMemStore())
	if e != nil {
		t.Fatal(e)
	}
	defer i.Close()
	idx := filepath.Join(d, "committed.idx")
	os.Remove(idx)
	if e = os.Symlink("committed.idx", idx); e != nil {
		t.Fatal(e)
	}
	rc, e := i.Accept("a", r, config.Usage{FreeBytes: 1 << 40})
	if e == nil || rc.Seq != 1 {
		t.Fatalf("expected durable accepted error: %+v %v", rc, e)
	}
	os.Remove(idx)
	os.WriteFile(idx, nil, 0600)
	r.MessageID = "b"
	if _, e = i.Accept("b", r, config.Usage{FreeBytes: 1 << 40}); e == nil {
		n, _ := i.w.Bytes()
		t.Fatalf("counter reseed failed silently; later accept exceeds cap actual=%d cap=%d counter=%d", n, cfg.WALBytes, i.walBytes)
	}
}
func TestCodexV3LegacySamePayloadReplay(t *testing.T) {
	for _, full := range []bool{false, true} {
		t.Run(map[bool]string{false: "ample", true: "at-cap"}[full], func(t *testing.T) {
			d := t.TempDir()
			r := archive.Record{Project: "p", SourceInstance: "i", SessionID: "s", MessageID: "m", Text: "same"}
			b, _ := json.Marshal(r)
			cfg := config.Default()
			if full {
				cfg.WALBytes = wal.RecordCost("p|i|s|m", b)
			}
			i, e := Open(d, config.NewAccountant(cfg), archive.NewMemStore())
			if e != nil {
				t.Fatal(e)
			}
			i.Accept("p|i|s|m", r, config.Usage{FreeBytes: 1 << 40})
			i.Close()
			i, e = Open(d, config.NewAccountant(cfg), archive.NewMemStore())
			if e != nil {
				t.Fatal(e)
			}
			defer i.Close()
			rc, e := i.Accept(archive.IdentityKey(r), r, config.Usage{FreeBytes: 1 << 40})
			if e != nil {
				t.Fatalf("benign legacy replay rejected: %v", e)
			}
			n, _ := i.AcceptedCount()
			if !rc.Duplicate || n != 1 {
				t.Fatalf("benign replay appended second WAL frame: duplicate=%v count=%d", rc.Duplicate, n)
			}
		})
	}
}
func TestCodexV3LegacyConflictAfterRestartCompact(t *testing.T) {
	d := t.TempDir()
	r := archive.Record{Project: "p", SourceInstance: "i", SessionID: "s", MessageID: "m", Text: "same"}
	cfg := config.NewAccountant(config.Default())
	s := archive.NewMemStore()
	i, e := Open(d, cfg, s)
	if e != nil {
		t.Fatal(e)
	}
	i.Accept("p|i|s|m", r, config.Usage{FreeBytes: 1 << 40})
	i.Close()
	i, e = Open(d, cfg, s)
	if e != nil {
		t.Fatal(e)
	}
	defer i.Close()
	if _, e = i.Compact(func(archive.Record) bool { return true }); e != nil {
		t.Fatal(e)
	}
	r.Text = "conflict"
	if _, e = i.Accept(archive.IdentityKey(r), r, config.Usage{FreeBytes: 1 << 40}); !errors.Is(e, wal.ErrKeyConflict) {
		t.Fatalf("expected conflict before WAL write %v", e)
	}
	if n, _ := i.AcceptedCount(); n != 1 {
		t.Fatalf("conflict added frame %d", n)
	}
	if n, e := i.Drain(); n != 1 || e != nil {
		t.Fatalf("drain poisoned %d %v", n, e)
	}
}
func TestCodexV3AcceptedErrorSameKeyRetryThenReopen(t *testing.T) {
	d := t.TempDir()
	r := archive.Record{Project: "p", MessageID: "a"}
	cfg := config.NewAccountant(config.Default())
	i, e := Open(d, cfg, archive.NewMemStore())
	if e != nil {
		t.Fatal(e)
	}
	idx := filepath.Join(d, "committed.idx")
	os.Remove(idx)
	os.Mkdir(idx, 0700)
	rc, e := i.Accept("a", r, config.Usage{FreeBytes: 1 << 40})
	if e == nil || rc.Seq != 1 {
		t.Fatalf("bad fault setup %+v %v", rc, e)
	}
	os.Remove(idx)
	os.WriteFile(idx, nil, 0600)
	rc, e = i.Accept("a", r, config.Usage{FreeBytes: 1 << 40})
	if e != nil || !rc.Duplicate {
		t.Fatalf("retry not deduped %+v %v", rc, e)
	}
	i.Close()
	i, e = Open(d, cfg, archive.NewMemStore())
	if e != nil {
		t.Fatal(e)
	}
	defer i.Close()
	if n, e := i.Drain(); n != 1 || e != nil {
		t.Fatalf("reopen lost accepted record %d %v", n, e)
	}
}
