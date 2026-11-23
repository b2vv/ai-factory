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

// T29: a backend outage between Reserve and Finish leaves the ingest intent of a record the WAL has
// accepted. While the sampler still fails, capture stays refused; once it works again the next
// capture proves the intent from the WAL (as start-up does) and proceeds without a restart.
// An intent the WAL does not prove keeps blocking.
func TestPendingIngestIntentRecoversAfterSamplerReturns(t *testing.T) {
	root := t.TempDir()
	dir := filepath.Join(root, "wal")
	cfg := config.Default()
	cfg.FreeHeadroom = 0
	store := archive.NewMemStore()
	i, e := Open(dir, config.NewAccountant(cfg), store)
	if e != nil {
		t.Fatal(e)
	}
	defer i.Close()
	calls, failFrom, failTo := 0, -1, -1
	outage := errors.New("synthetic backend outage")
	sample := func() (budget.Sample, error) {
		calls++
		if calls >= failFrom && calls <= failTo {
			return budget.Sample{}, outage
		}
		return budget.LocalSample(root, cfg.LiveCapBytes)
	}
	l, e := budget.Initialize(filepath.Join(root, "budget.bin"), budget.Policy{LiveCap: cfg.LiveCapBytes}, sample)
	if e != nil {
		t.Fatal(e)
	}
	defer l.Close()
	if e = i.SetBudget(l); e != nil {
		t.Fatal(e)
	}
	usage := config.Usage{FreeBytes: 1 << 40}
	m2 := archive.Record{Project: "p", MessageID: "m2", Text: "synthetic"}
	failFrom, failTo = calls+2, calls+1000 // Reserve samples fine, Finish hits the outage
	if rc, e := i.Accept(archive.IdentityKey(m2), m2, usage); !errors.Is(e, outage) || rc.Seq == 0 {
		t.Fatal("expected an accepted record with an unfinished intent", rc, e)
	}
	if p := l.Snapshot().Pending; len(p) != 1 || p[0].Evidence.Kind != "ingest" {
		t.Fatal("ingest intent not retained", p)
	}
	m3 := archive.Record{Project: "p", MessageID: "m3", Text: "synthetic"}
	if rc, e := i.Accept(archive.IdentityKey(m3), m3, usage); e == nil || rc.Seq != 0 {
		t.Fatal("capture must stay refused while the backend is down", rc, e)
	}
	failTo = calls // the backend is back
	if rc, e := i.Accept(archive.IdentityKey(m3), m3, usage); e != nil || rc.Duplicate {
		t.Fatal("capture did not recover", rc, e)
	}
	if p := l.Snapshot().Pending; len(p) != 0 {
		t.Fatal("liability left after recovery", p)
	}
	if _, e = i.Drain(); e != nil {
		t.Fatal(e)
	}
	if got := len(store.All("p")); got != 2 {
		t.Fatal("m2 (accepted during the outage) and m3 must both drain; got", got)
	}
	// An intent no accepted record proves is never resolved by this path.
	if e = l.Reserve(intent("ingest", "unproven", []byte("x")), 0); e != nil {
		t.Fatal(e)
	}
	m4 := archive.Record{Project: "p", MessageID: "m4", Text: "synthetic"}
	if rc, e := i.Accept(archive.IdentityKey(m4), m4, usage); !errors.Is(e, budget.ErrBlocked) || rc.Seq != 0 {
		t.Fatal("unproven intent must keep blocking", rc, e)
	}
}
