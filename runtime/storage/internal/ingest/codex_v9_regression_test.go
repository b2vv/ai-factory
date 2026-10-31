package ingest

import (
	"aifactory.local/storage/internal/archive"
	"aifactory.local/storage/internal/config"
	"testing"
)

func TestReviewerV9LegacyCanonicalReceipt(t *testing.T) {
	d := t.TempDir()
	cfg := config.NewAccountant(config.Default())
	s := archive.NewMemStore()
	i, e := Open(d, cfg, s)
	if e != nil {
		t.Fatal(e)
	}
	r := archive.Record{Project: "p", SourceInstance: "i", SessionID: "s", MessageID: "a"}
	i.Accept("p|i|s|a", r, config.Usage{FreeBytes: 1 << 40})
	i.Close()
	i, e = Open(d, cfg, s)
	if e != nil {
		t.Fatal(e)
	}
	defer i.Close()
	key := archive.IdentityKey(r)
	rc, e := i.Accept(key, r, config.Usage{FreeBytes: 1 << 40})
	if e != nil || !rc.Duplicate {
		t.Fatal(rc, e)
	}
	st, e := i.RecordState(rc.Key, "p")
	if e != nil {
		t.Fatal(e)
	}
	if st.State != "durable_accepted" {
		t.Fatalf("duplicate-success receipt lost: %+v", st)
	}
}
func TestReviewerV9QuarantineProgress(t *testing.T) {
	d := t.TempDir()
	cfg := config.NewAccountant(config.Default())
	s := archive.NewMemStore()
	i, e := Open(d, cfg, s)
	if e != nil {
		t.Fatal(e)
	}
	r := archive.Record{Project: "p", MessageID: "a"}
	key := archive.IdentityKey(r)
	i.Accept(key, r, config.Usage{FreeBytes: 1 << 40})
	i.DrainGated(func(archive.Record) bool { return false })
	i.Close()
	i, e = Open(d, cfg, s)
	if e != nil {
		t.Fatal(e)
	}
	defer i.Close()
	st, e := i.RecordState(key, "p")
	if e != nil || st.State != "quarantined" {
		t.Fatal(st, e)
	}
	p, e := i.Progress()
	if e != nil {
		t.Fatal(e)
	}
	t.Logf("receipt=%s progress=%+v archive-records=0", st.State, p)
	if p.Processed != 1 || p.Depth != 0 {
		t.Fatalf("quarantine processing not accounted: %+v", p)
	}
}
func TestReviewerV9CompactionReceiptBoundary(t *testing.T) {
	i, e := Open(t.TempDir(), config.NewAccountant(config.Default()), archive.NewMemStore())
	if e != nil {
		t.Fatal(e)
	}
	defer i.Close()
	a := archive.Record{Project: "p", MessageID: "a"}
	ka := archive.IdentityKey(a)
	ra, e := i.Accept(ka, a, config.Usage{FreeBytes: 1 << 40})
	if e != nil {
		t.Fatal(e)
	}
	i.Drain()
	if _, e = i.Compact(func(archive.Record) bool { return false }); e != nil {
		t.Fatal(e)
	}
	b := archive.Record{Project: "q", MessageID: "b"}
	kb := archive.IdentityKey(b)
	rb, e := i.Accept(kb, b, config.Usage{FreeBytes: 1 << 40})
	if e != nil {
		t.Fatal(e)
	}
	sa, _ := i.RecordState(ka, "p")
	sb, _ := i.RecordState(kb, "q")
	t.Logf("primitive drop-all: oldSeq=%d newSeq=%d oldState=%s newState=%s; archive lookup preserves reclaimed receipts", ra.Seq, rb.Seq, sa.State, sb.State)
	if sa.State != "archive_committed" || sb.State != "durable_accepted" {
		t.Fatal(sa, sb)
	}
}
