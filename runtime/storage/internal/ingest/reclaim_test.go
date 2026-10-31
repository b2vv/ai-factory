package ingest

import (
	"aifactory.local/storage/internal/archive"
	"aifactory.local/storage/internal/config"
	"aifactory.local/storage/internal/wal"
	"errors"
	"os"
	"path/filepath"
	"testing"
)

func TestReclaimPreservesReceiptsQuarantineAndReplay(t *testing.T) {
	d := t.TempDir()
	s := archive.NewMemStore()
	cfg := config.NewAccountant(config.Default())
	i, e := Open(d, cfg, s)
	if e != nil {
		t.Fatal(e)
	}
	u := config.Usage{FreeBytes: 1 << 40}
	a := archive.Record{Project: "p", MessageID: "a", Text: "published"}
	b := archive.Record{Project: "q", MessageID: "b", Text: "quarantine"}
	ka, kb := archive.IdentityKey(a), archive.IdentityKey(b)
	i.Accept(ka, a, u)
	i.Accept(kb, b, u)
	i.DrainGated(func(r archive.Record) bool { return r.Project == "p" })
	before := i.WALBytes()
	res, e := i.Reclaim()
	if e != nil || res.Dropped != 1 {
		t.Fatal(res, e)
	}
	if i.WALBytes() >= before {
		t.Fatal("no space freed")
	}
	if n, _ := i.AcceptedCount(); n != 1 {
		t.Fatal("quarantine lost")
	}
	i.Close()
	i, e = Open(d, cfg, s)
	if e != nil {
		t.Fatal(e)
	}
	defer i.Close()
	st, e := i.RecordState(ka, "p")
	if e != nil || st.State != "archive_committed" {
		t.Fatal(st, e)
	}
	st, e = i.RecordState(kb, "q")
	if e != nil || st.State != "quarantined" {
		t.Fatal(st, e)
	}
	rc, e := i.Accept(ka, a, u)
	if e != nil || !rc.Duplicate {
		t.Fatal(rc, e)
	}
	a.Text = "conflict"
	if _, e = i.Accept(ka, a, u); !errors.Is(e, wal.ErrKeyConflict) {
		t.Fatal("lost conflict", e)
	}
	s.SetAvailable(false)
	a.MessageID = "new"
	if _, e = i.Accept(archive.IdentityKey(a), a, u); e == nil {
		t.Fatal("reclaimed dedup guessed archive absence")
	}
}
func TestReclaimMarkerFailurePreservesFrames(t *testing.T) {
	d := t.TempDir()
	s := archive.NewMemStore()
	i, e := Open(d, config.NewAccountant(config.Default()), s)
	if e != nil {
		t.Fatal(e)
	}
	defer i.Close()
	r := archive.Record{Project: "p", MessageID: "m"}
	i.Accept(archive.IdentityKey(r), r, config.Usage{FreeBytes: 1 << 40})
	i.Drain()
	os.Mkdir(filepath.Join(d, "reclaimed"), 0700)
	if _, e = i.Reclaim(); e == nil {
		t.Fatal("marker fault ignored")
	}
	if n, _ := i.AcceptedCount(); n != 1 {
		t.Fatal("removed before marker durable")
	}
	if _, e = i.Reclaim(); e == nil {
		t.Fatal("retry bypassed missing durable marker")
	}
}
func TestReclaimPreservesOpaqueHistoricalReceipt(t *testing.T) {
	s := archive.NewMemStore()
	i, e := Open(t.TempDir(), config.NewAccountant(config.Default()), s)
	if e != nil {
		t.Fatal(e)
	}
	defer i.Close()
	r := archive.Record{Project: "p", MessageID: "old"}
	i.Accept("old-receipt", r, config.Usage{FreeBytes: 1 << 40})
	i.Drain()
	if _, e = i.Reclaim(); e != nil {
		t.Fatal(e)
	}
	st, e := i.RecordState("old-receipt", "p")
	if e != nil || st.State != "archive_committed" {
		t.Fatal("lost historical receipt", st, e)
	}
}
