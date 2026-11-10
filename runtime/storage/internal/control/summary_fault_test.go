package control

import (
	"aifactory.local/storage/internal/budget"
	"aifactory.local/storage/internal/config"
	"aifactory.local/storage/internal/wal"
	"encoding/json"
	"errors"
	"math"
	"path/filepath"
	"testing"
)

// Arrange the boundary directly, like the existing closed-WAL fault fixtures.
// Assertions use public mutation, retained WAL and reopen behavior, not 2^64 calls.
func TestSummaryExhaustedPolicyRetainsTerminalRevoke(t *testing.T) {
	dir := t.TempDir()
	d := mustInit(t, dir)
	if e := d.MintProject(operator(), "p", "fixture"); e != nil {
		t.Fatal(e)
	}
	d.archiveStates = map[string]ArchiveState{"p": {Generation: "g", Version: 2, MigrationComplete: true, NextOrdinal: 1, PolicyRevision: math.MaxUint64}}
	_, e := d.SetConsent(operator(), "p", "synthetic", "summary", false)
	if !errors.Is(e, ErrBlocked) {
		d.Close()
		t.Fatal("terminal operation acknowledged", e)
	}
	if blocked, _ := d.Blocked(); !blocked {
		d.Close()
		t.Fatal("exhausted policy kept serving authority")
	}
	if e = d.Close(); e != nil {
		t.Fatal(e)
	}
	records, report, e := wal.Accepted(filepath.Join(dir, "wal"))
	if e != nil || report.IsBlocked() {
		t.Fatal("witness not durably inspectable", e)
	}
	var last map[string]any
	if e = json.Unmarshal(records[len(records)-1].Payload, &last); e != nil {
		t.Fatal(e)
	}
	proof, ok := last["summary_consent"].(map[string]any)
	if !ok || last["kind"] != "summary_consent_v1" || (last["enabled"] != nil && last["enabled"] != false) || proof["terminal"] != true {
		t.Fatal("terminal revoke persistence was skipped", last)
	}
	// The retained terminal witness itself denies reopening even when this fixture's
	// injected max revision was not established by an infeasible operator history.
	got, e := Open(dir)
	if e != nil && !errors.Is(e, ErrSummaryTerminal) {
		t.Fatal("unrelated error is not terminal refusal", e)
	}
	if e == nil {
		blocked, _ := got.Blocked()
		got.Close()
		if !blocked {
			t.Fatal("terminal witness lost on reopen")
		}
	}
}

func TestSummaryEnablePolicyExhaustionRefusesBeforePersist(t *testing.T) {
	dir := t.TempDir()
	cfg := config.Default()
	cfg.FreeHeadroom = 0
	d, e := InitializeBudgeted(dir, cfg)
	if e != nil {
		t.Fatal(e)
	}
	defer d.Close()
	if e = d.MintProject(operator(), "p", "fixture"); e != nil {
		t.Fatal(e)
	}
	if e = d.BeginArchiveMigration(operator(), "p", "g"); e != nil {
		t.Fatal(e)
	}
	l, e := budget.Open(filepath.Join(dir, "budget.bin"), func() (budget.Sample, error) { return budget.LocalSample(dir, cfg.LiveCapBytes) })
	if e != nil {
		t.Fatal(e)
	}
	if e = d.AttachBudget(l); e != nil {
		t.Fatal(e)
	}
	if e = d.WithArchiveTransaction(operator(), "p", func(tx *ArchiveTransaction) error { return tx.FinishMigration(func(ArchiveState) error { return nil }) }); e != nil {
		t.Fatal(e)
	}
	state := d.archiveStates["p"]
	state.PolicyRevision = math.MaxUint64
	d.archiveStates["p"] = state
	before, _, e := wal.Accepted(filepath.Join(dir, "wal"))
	if e != nil {
		t.Fatal(e)
	}
	if _, e = d.SetConsent(operator(), "p", "synthetic", "summary", true); e == nil {
		t.Fatal("exhausted policy grant accepted")
	}
	after, _, e := wal.Accepted(filepath.Join(dir, "wal"))
	if e != nil || len(after) != len(before) {
		t.Fatal("invalid grant retained a poisoning witness", e)
	}
	if blocked, why := d.Blocked(); blocked {
		t.Fatal("prevalidation refusal poisoned live authority", why)
	}
}
