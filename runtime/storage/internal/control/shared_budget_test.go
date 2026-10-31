package control

import (
	"aifactory.local/storage/internal/authz"
	"aifactory.local/storage/internal/budget"
	"aifactory.local/storage/internal/config"
	"aifactory.local/storage/internal/registry"
	"errors"
	"os"
	"path/filepath"
	"testing"
)

func TestBudgetRefusalDoesNotAcknowledgeOrExposeAuthority(t *testing.T) {
	for _, revoke := range []bool{false, true} {
		name := "grant"
		if revoke {
			name = "revoke"
		}
		t.Run(name, func(t *testing.T) {
			d := mustInit(t, t.TempDir())
			defer d.Close()
			token := seed(t, d, "p", "a", "synthetic")
			before, e := d.w.Bytes()
			if e != nil {
				t.Fatal(e)
			}
			reserved := d.ReservedBytes()
			d.SetCapacityCheck(func(int64) error { return errors.New("synthetic full budget") })
			if revoke {
				e = d.RevokeGrant(operator(), "a")
			} else {
				e = d.IssueGrant(operator(), agentGrant("b", "p", "synthetic-b"))
			}
			if !errors.Is(e, ErrCapacity) {
				t.Fatalf("expected explicit pre-write capacity refusal: %v", e)
			}
			after, e := d.w.Bytes()
			if e != nil || after != before {
				t.Fatalf("rejected mutation wrote WAL: before=%d after=%d err=%v", before, after, e)
			}
			if d.ReservedBytes() != reserved {
				t.Fatal("rejected write changed committed accounting")
			}
			if e = authz.Authorize(d.Registry(), token, "p", registry.OpArchiveQuery); e == nil {
				t.Fatal("capacity failure exposed authority")
			}
		})
	}
}

func TestBudgetedInitializationRejectsBeforeNonemptyMetadata(t *testing.T) {
	dir := t.TempDir()
	cfg := config.Default()
	cfg.LiveCapBytes = budget.FileBytes
	cfg.FreeHeadroom = 0
	if d, e := InitializeBudgeted(dir, cfg); e == nil {
		d.Close()
		t.Fatal("bootstrap bypassed cap")
	}
	for _, name := range []string{"control.meta", "control.meta.tmp", "budget.bin"} {
		if _, e := os.Stat(filepath.Join(dir, name)); !os.IsNotExist(e) {
			t.Fatal("refused initialization wrote metadata", name, e)
		}
	}
}

func TestUnrelatedNoopCannotReleaseFailedExternalReservation(t *testing.T) {
	dir := t.TempDir()
	cfg := config.Default()
	cfg.FreeHeadroom = 0
	d, e := InitializeBudgeted(dir, cfg)
	if e != nil {
		t.Fatal(e)
	}
	defer d.Close()
	l, e := budget.Open(filepath.Join(dir, "budget.bin"), func() (budget.Sample, error) { return budget.LocalSample(dir, cfg.LiveCapBytes) })
	if e != nil {
		t.Fatal(e)
	}
	if e = d.AttachBudget(l); e != nil {
		t.Fatal(e)
	}
	if e = d.WithStableAuthority(operator(), func(*registry.Registry) error {
		if e := d.ReserveExternalBytes(100); e != nil {
			return e
		}
		return errors.New("synthetic ambiguous external result")
	}); e == nil {
		t.Fatal("fault not propagated")
	}
	if e = d.WithStableAuthority(operator(), func(*registry.Registry) error { return d.FinishExternal() }); !errors.Is(e, budget.ErrBlocked) {
		t.Fatal("unrelated no-op discharged pending liability", e)
	}
	if len(l.Snapshot().Pending) != 1 {
		t.Fatal("lost reservation")
	}
}
