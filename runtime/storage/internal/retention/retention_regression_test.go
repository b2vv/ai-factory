package retention

// Regression tests for interim-review finding IR6: Restore is a replay/serve admission
// gate and must FAIL CLOSED. It must not serve archived records when no current
// authority is established, and re-enabling consent must not retroactively resurrect
// records captured under a superseded (pre-revocation) consent epoch.

import (
	"testing"

	"aifactory.local/storage/internal/archive"
	"aifactory.local/storage/internal/registry"
)

func op() registry.Principal { return registry.Principal{ID: "op", Kind: registry.Operator} }

// IR6a — Restore with no established authority must withhold everything. Reviewer
// evidence (restore_without_authority): the buggy tree returns 1 record from a fresh
// registry with no project/consent.
func TestIR6_RestoreFailsClosedWithoutAuthority(t *testing.T) {
	reg := registry.New() // nothing minted, no consent established
	m := New(reg)
	rec := archive.Record{Project: "p", Provider: "prov", Type: archive.TypeMessage, ConsentEpoch: 1, Text: "hi"}

	out := m.Restore([]archive.Record{rec}, "capture")
	if len(out) != 0 {
		t.Fatalf("IR6: Restore served %d record(s) without established authority; must fail closed", len(out))
	}
}

// IR6b — re-enabling consent must not resurrect pre-revocation records. Reviewer
// evidence (reenable_old_epoch): enabled(e1) -> revoked(e2) -> enabled(e3); a record
// captured under e1 is returned by the buggy tree.
func TestIR6_ReenableDoesNotResurrectPreRevocationData(t *testing.T) {
	reg := registry.New()
	if err := reg.MintProject(op(), "p", "P"); err != nil {
		t.Fatal(err)
	}
	if _, err := reg.SetConsent(op(), "p", "prov", "capture", true); err != nil { // epoch 1
		t.Fatal(err)
	}
	if _, err := reg.SetConsent(op(), "p", "prov", "capture", false); err != nil { // epoch 2 (revoked)
		t.Fatal(err)
	}
	e3, err := reg.SetConsent(op(), "p", "prov", "capture", true) // epoch 3 (re-enabled)
	if err != nil {
		t.Fatal(err)
	}

	m := New(reg)
	old := archive.Record{Project: "p", Provider: "prov", Type: archive.TypeMessage, ConsentEpoch: 1, Text: "old"}
	cur := archive.Record{Project: "p", Provider: "prov", Type: archive.TypeMessage, ConsentEpoch: e3, Text: "current"}

	out := m.Restore([]archive.Record{old, cur}, "capture")
	// The pre-revocation record must be withheld; the current-epoch record is allowed.
	for _, r := range out {
		if r.ConsentEpoch < e3 {
			t.Fatalf("IR6: Restore resurrected a pre-revocation record (epoch %d < current %d)", r.ConsentEpoch, e3)
		}
	}
	if len(out) != 1 || out[0].Text != "current" {
		t.Fatalf("IR6: expected only the current-epoch record to restore, got %+v", out)
	}
}
