package ingest

import (
	"aifactory.local/storage/internal/wal"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"aifactory.local/storage/internal/archive"
	"aifactory.local/storage/internal/budget"
	"aifactory.local/storage/internal/config"
)

func TestDurableBudgetExplicitReclaimFixedLimitCycles(t *testing.T) {
	root := t.TempDir()
	dir := filepath.Join(root, "wal")
	cfg := config.Default()
	cfg.WALBytes = 2048
	cfg.LiveCapBytes = budget.FileBytes + 20000
	cfg.FreeHeadroom = 0
	store := archive.NewMemStore()
	i, e := Open(dir, config.NewAccountant(cfg), store)
	if e != nil {
		t.Fatal(e)
	}
	sample := func() (budget.Sample, error) {
		s, e := budget.LocalSample(root, cfg.LiveCapBytes)
		if e != nil {
			return s, e
		}
		var bytes int64
		for _, r := range store.All("p") {
			bytes += archive.ReservationBytes(r)
		}
		s.Components["archive"] = bytes
		debt, e := PendingLogicalBytes(dir, cfg.WALBytes, store)
		s.Components["pending"] = debt
		return s, e
	}
	ledger, e := budget.Initialize(filepath.Join(root, "budget.bin"), budget.Policy{LiveCap: cfg.LiveCapBytes}, sample)
	if e != nil {
		t.Fatal(e)
	}
	if e = i.SetBudget(ledger); e != nil {
		t.Fatal(e)
	}
	for n := 0; n < 10; n++ {
		r := archive.Record{Project: "p", MessageID: fmt.Sprint(n), Text: strings.Repeat("x", 128)}
		if _, e = i.Accept(archive.IdentityKey(r), r, config.Usage{FreeBytes: 1 << 40}); e != nil {
			t.Fatal(n, e)
		}
		if _, e = i.Drain(); e != nil {
			t.Fatal(n, e)
		}
		if out, e := i.Reclaim(); e != nil || out.Dropped != 1 {
			t.Fatal(n, out, e)
		}
		if len(ledger.Snapshot().Pending) != 0 {
			t.Fatal("maintenance liability unresolved")
		}
		i.Close()
		ledger.Close()
		i, e = Open(dir, config.NewAccountant(cfg), store)
		if e != nil {
			t.Fatal(e)
		}
		ledger, e = budget.Open(filepath.Join(root, "budget.bin"), sample)
		if e != nil {
			t.Fatal(e)
		}
		if e = i.SetBudget(ledger); e != nil {
			t.Fatal(e)
		}
		if rc, e := i.Accept(archive.IdentityKey(r), r, config.Usage{FreeBytes: 1 << 40}); e != nil || !rc.Duplicate {
			t.Fatal(rc, e)
		}
		state, e := i.RecordState(archive.IdentityKey(r), "p")
		if e != nil || state.State != "archive_committed" {
			t.Fatal(state, e)
		}
	}
	i.Close()
	ledger.Close()
}

func TestLedgerDurableAcceptErrorReopenKeepsDebtAndRejectsConflict(t *testing.T) {
	root := t.TempDir()
	dir := filepath.Join(root, "wal")
	cfg := config.Default()
	cfg.FreeHeadroom = 0
	store := archive.NewMemStore()
	i, e := Open(dir, config.NewAccountant(cfg), store)
	if e != nil {
		t.Fatal(e)
	}
	inject := false
	sample := func() (budget.Sample, error) {
		s, e := budget.LocalSample(root, cfg.LiveCapBytes)
		if e != nil {
			return s, e
		}
		debt, e := PendingLogicalBytes(dir, cfg.WALBytes, store)
		if e != nil {
			return s, e
		}
		s.Components["pending"] = debt
		if inject {
			inject = false
			idx := filepath.Join(dir, "committed.idx")
			if e = os.Remove(idx); e != nil {
				return s, e
			}
			if e = os.Mkdir(idx, 0700); e != nil {
				return s, e
			}
		}
		return s, nil
	}
	l, e := budget.Initialize(filepath.Join(root, "budget.bin"), budget.Policy{LiveCap: cfg.LiveCapBytes}, sample)
	if e != nil {
		t.Fatal(e)
	}
	if e = i.SetBudget(l); e != nil {
		t.Fatal(e)
	}
	r := archive.Record{Project: "p", MessageID: "m", Text: "synthetic"}
	key := archive.IdentityKey(r)
	inject = true
	if rc, e := i.Accept(key, r, config.Usage{FreeBytes: 1 << 40}); e == nil || rc.Seq != 1 {
		t.Fatal(rc, e)
	}
	if len(l.Snapshot().Pending) != 1 {
		t.Fatal("ambiguous acceptance liability disappeared")
	}
	idx := filepath.Join(dir, "committed.idx")
	if e = os.Remove(idx); e != nil {
		t.Fatal(e)
	}
	if e = os.WriteFile(idx, nil, 0600); e != nil {
		t.Fatal(e)
	}
	i.Close()
	l.Close()
	i, e = Open(dir, config.NewAccountant(cfg), store)
	if e != nil {
		t.Fatal(e)
	}
	defer i.Close()
	l, e = budget.Open(filepath.Join(root, "budget.bin"), sample)
	if e != nil {
		t.Fatal(e)
	}
	defer l.Close()
	if e = i.SetBudget(l); e != nil {
		t.Fatal(e)
	}
	if len(l.Snapshot().Pending) != 0 || l.Snapshot().Components["pending"] < archive.ReservationBytes(r) {
		t.Fatal("recovery dropped accepted projection debt")
	}
	if rc, e := i.Accept(key, r, config.Usage{FreeBytes: 1 << 40}); e != nil || !rc.Duplicate {
		t.Fatal(rc, e)
	}
	different := r
	different.MessageID = "other"
	if _, e = i.Accept(key, different, config.Usage{FreeBytes: 1 << 40}); !errors.Is(e, wal.ErrKeyConflict) {
		t.Fatal(e)
	}
	if len(l.Snapshot().Pending) != 0 {
		t.Fatal("known no-write conflict poisoned accounting")
	}
}
