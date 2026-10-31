package ingest

import (
	"aifactory.local/storage/internal/archive"
	"aifactory.local/storage/internal/config"
	"aifactory.local/storage/internal/wal"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"testing"
)

func TestReclaimBudgetRefusesBeforeMarkerAndCheckpoint(t *testing.T) {
	dir := t.TempDir()
	store := archive.NewMemStore()
	cfg := config.Default()
	i, e := Open(dir, config.NewAccountant(cfg), store)
	if e != nil {
		t.Fatal(e)
	}
	defer i.Close()
	for _, p := range []string{"published", "quarantine"} {
		r := archive.Record{Project: p, MessageID: "m", Text: "payload"}
		if _, e = i.Accept(archive.IdentityKey(r), r, config.Usage{FreeBytes: 1 << 40}); e != nil {
			t.Fatal(e)
		}
	}
	if _, e = i.DrainGated(func(r archive.Record) bool { return r.Project == "published" }); e != nil {
		t.Fatal(e)
	}
	before, _ := os.ReadFile(i.wmPath)
	cfg.WALBytes, _ = wal.ManagedBytes(dir)
	i.acct = config.NewAccountant(cfg)
	if _, e = i.Reclaim(); !errors.Is(e, wal.ErrMaintenanceBudget) {
		t.Fatal("expected staged peak refusal", e)
	}
	after, _ := os.ReadFile(i.wmPath)
	if string(before) != string(after) {
		t.Fatal("watermark changed before reservation")
	}
	if _, e = os.Stat(filepath.Join(dir, "reclaimed")); !os.IsNotExist(e) {
		t.Fatal("marker written before reservation", e)
	}
	if n, e := i.AcceptedCount(); e != nil || n != 2 {
		t.Fatal(n, e)
	}
}
func TestReclaimScanMakesProgressBeyondQuarantineWindow(t *testing.T) {
	i, e := Open(t.TempDir(), config.NewAccountant(config.Default()), archive.NewMemStore())
	if e != nil {
		t.Fatal(e)
	}
	defer i.Close()
	for n := 0; n < 140; n++ {
		p := "q"
		if n == 139 {
			p = "p"
		}
		r := archive.Record{Project: p, MessageID: fmt.Sprint(n)}
		if _, e = i.Accept(archive.IdentityKey(r), r, config.Usage{FreeBytes: 1 << 40}); e != nil {
			t.Fatal(e)
		}
	}
	if _, e = i.DrainGated(func(r archive.Record) bool { return r.Project == "p" }); e != nil {
		t.Fatal(e)
	}
	first, e := i.Reclaim()
	if e != nil || first.Dropped != 0 {
		t.Fatal(first, e)
	}
	// A concurrent producer extends the old snapshot between bounded steps.
	r := archive.Record{Project: "q", MessageID: "concurrent-tail"}
	if _, e = i.Accept(archive.IdentityKey(r), r, config.Usage{FreeBytes: 1 << 40}); e != nil {
		t.Fatal(e)
	}
	second, e := i.Reclaim()
	if e != nil || second.Dropped != 1 {
		t.Fatal(second, e)
	}
	if n, e := i.AcceptedCount(); e != nil || n != 140 {
		t.Fatal("quarantine was lost", n, e)
	}
}

func TestReclaimGatedRetainsWithheldRecordAlreadyInArchive(t *testing.T) {
	store := archive.NewMemStore()
	i, e := Open(t.TempDir(), config.NewAccountant(config.Default()), store)
	if e != nil {
		t.Fatal(e)
	}
	defer i.Close()
	withheld := archive.Record{Project: "q", MessageID: "old"}
	allowed := archive.Record{Project: "p", MessageID: "new"}
	for _, r := range []archive.Record{withheld, allowed} {
		if _, e = i.Accept(archive.IdentityKey(r), r, config.Usage{FreeBytes: 1 << 40}); e != nil {
			t.Fatal(e)
		}
	}
	if _, e = i.Drain(); e != nil {
		t.Fatal(e)
	}
	result, e := i.ReclaimGated(func(r archive.Record) bool { return r.Project == "p" })
	if e != nil || result.Dropped != 1 {
		t.Fatal(result, e)
	}
	if !i.w.Has(archive.IdentityKey(withheld)) {
		t.Fatal("policy-withheld WAL evidence reclaimed")
	}
	if i.w.Has(archive.IdentityKey(allowed)) {
		t.Fatal("eligible source not reclaimed")
	}
}

func TestReclaimMeasuredLiveBudgetCannotBeSpentAsWALHeadroom(t *testing.T) {
	i, e := Open(t.TempDir(), config.NewAccountant(config.Default()), archive.NewMemStore())
	if e != nil {
		t.Fatal(e)
	}
	defer i.Close()
	r := archive.Record{Project: "p", MessageID: "m"}
	if _, e = i.Accept(archive.IdentityKey(r), r, config.Usage{FreeBytes: 1 << 40}); e != nil {
		t.Fatal(e)
	}
	if _, e = i.Drain(); e != nil {
		t.Fatal(e)
	}
	current, e := wal.ManagedBytes(i.dir)
	if e != nil {
		t.Fatal(e)
	}
	if _, e = i.ReclaimBudgeted(nil, current); !errors.Is(e, wal.ErrMaintenanceBudget) {
		t.Fatal("live budget ignored", e)
	}
	if n, e := i.AcceptedCount(); e != nil || n != 1 {
		t.Fatal(n, e)
	}
}

func TestReclaimUsageRetainsPendingDebtAcrossRestart(t *testing.T) {
	dir := t.TempDir()
	store := archive.NewMemStore()
	cfg := config.Default()
	i, e := Open(dir, config.NewAccountant(cfg), store)
	if e != nil {
		t.Fatal(e)
	}
	r := archive.Record{Project: "p", MessageID: "pending", Text: "payload"}
	if _, e = i.Accept(archive.IdentityKey(r), r, config.Usage{FreeBytes: 1 << 40}); e != nil {
		t.Fatal(e)
	}
	debt := i.PendingArchiveBytes()
	if debt <= 0 {
		t.Fatal("fixture has no pending liability")
	}
	i.Close()
	i, e = Open(dir, config.NewAccountant(cfg), store)
	if e != nil {
		t.Fatal(e)
	}
	defer i.Close()
	before, e := wal.ManagedBytes(dir)
	if e != nil {
		t.Fatal(e)
	}
	usage := config.Usage{LiveBytes: cfg.LiveCapBytes - debt + 1, FreeBytes: 1 << 40}
	if _, e = i.ReclaimWithUsage(nil, usage); !errors.Is(e, wal.ErrMaintenanceBudget) {
		t.Fatalf("restart debt spent on staging: %v", e)
	}
	after, e := wal.ManagedBytes(dir)
	if e != nil || after != before {
		t.Fatalf("refusal wrote managed files: %d %d %v", before, after, e)
	}
	if n, e := i.AcceptedCount(); e != nil || n != 1 {
		t.Fatal("pending durable record changed", n, e)
	}
	// Exactly funded debt is valid when no projection is eligible for reclamation.
	usage.LiveBytes--
	if out, e := i.ReclaimWithUsage(nil, usage); e != nil || out.Dropped != 0 {
		t.Fatal(out, e)
	}
}
