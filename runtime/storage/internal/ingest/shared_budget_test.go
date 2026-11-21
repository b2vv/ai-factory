package ingest

import (
	"aifactory.local/storage/internal/archive"
	"aifactory.local/storage/internal/config"
	"aifactory.local/storage/internal/wal"
	"encoding/json"
	"path/filepath"
	"testing"
)

func TestSharedBudgetRejectsWALOnlyAllowance(t *testing.T) {
	r := msg("p", "s", "m", "payload")
	b, _ := json.Marshal(r)
	cfg := config.Default()
	cfg.LiveCapBytes = wal.RecordCost(archive.IdentityKey(r), b)
	i := newIngestor(t, archive.NewMemStore(), cfg)
	if _, e := i.Accept(archive.IdentityKey(r), r, bigUsage()); e == nil {
		t.Fatal("WAL-only allowance admitted both WAL and archive liability")
	}
	if n, _ := i.AcceptedCount(); n != 0 {
		t.Fatalf("rejected record became durable: %d", n)
	}
}

func TestSharedBudgetPendingDebtRestartAndQuarantine(t *testing.T) {
	dir := filepath.Join(t.TempDir(), "wal")
	store := archive.NewMemStore()
	cfg := config.Default()
	r := msg("p", "s", "m", "payload")
	key := archive.IdentityKey(r)
	i, e := Open(dir, config.NewAccountant(cfg), store)
	if e != nil {
		t.Fatal(e)
	}
	if _, e = i.Accept(key, r, bigUsage()); e != nil {
		t.Fatal(e)
	}
	debt := archive.ReservationBytes(r)
	if i.PendingArchiveBytes() != debt {
		t.Fatal("missing pending archive reservation")
	}
	i.Close()
	i, e = Open(dir, config.NewAccountant(cfg), store)
	if e != nil {
		t.Fatal(e)
	}
	defer i.Close()
	if i.PendingArchiveBytes() != debt {
		t.Fatal("restart lost archive liability")
	}
	before := i.ReservationBytes()
	if rc, e := i.Accept(key, r, config.Usage{}); e != nil || !rc.Duplicate {
		t.Fatalf("duplicate charged: %v %v", rc, e)
	}
	if i.ReservationBytes() != before || i.PendingArchiveBytes() != debt {
		t.Fatal("duplicate changed reservation")
	}
	if _, e = i.DrainGated(func(archive.Record) bool { return false }); e != nil {
		t.Fatal(e)
	}
	if i.PendingArchiveBytes() != 0 {
		t.Fatal("quarantine retained future projection liability")
	}
	if n, _ := i.AcceptedCount(); n != 1 {
		t.Fatal("quarantine discarded durable data")
	}
}

func TestSharedBudgetExactTwoRecordAllowance(t *testing.T) {
	r := msg("p", "s", "a", "payload")
	other := r
	other.MessageID = "b"
	cfg := config.Default()
	cfg.LiveCapBytes = RecordCost(r) + RecordCost(other)
	i := newIngestor(t, archive.NewMemStore(), cfg)
	if _, e := i.Accept(archive.IdentityKey(r), r, bigUsage()); e != nil {
		t.Fatal(e)
	}
	// Same measurement window: only newly written WAL is added here. Pending
	// projection liability is owned by the ingestor and must be counted once.
	u := bigUsage()
	u.LiveBytes = i.ReservationBytes()
	if _, e := i.Accept(archive.IdentityKey(other), other, u); e != nil {
		t.Fatalf("double-reserved pending debt: %v", e)
	}
	if _, e := i.Drain(); e != nil {
		t.Fatal(e)
	}
	if i.PendingArchiveBytes() != 0 {
		t.Fatal("committed projection still pending")
	}
}
