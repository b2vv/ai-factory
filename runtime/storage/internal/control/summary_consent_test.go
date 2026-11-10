package control_test

import (
	"aifactory.local/storage/internal/archive"
	"aifactory.local/storage/internal/budget"
	"aifactory.local/storage/internal/control"
	"aifactory.local/storage/internal/registry"
	"aifactory.local/storage/internal/wal"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"reflect"
	"strings"
	"testing"
	"time"
)

func summaryControl(t *testing.T) (*control.Durable, string, registry.Principal) {
	t.Helper()
	dir := t.TempDir()
	d, e := control.Initialize(dir)
	if e != nil {
		t.Fatal(e)
	}
	op := registry.Principal{ID: "fixture", Kind: registry.Operator}
	if e = d.MintProject(op, "p", "synthetic"); e != nil {
		t.Fatal(e)
	}
	if e = d.BeginArchiveMigration(op, "p", "g"); e != nil {
		t.Fatal(e)
	}
	attachArchiveLedger(t, d, dir)
	if e = d.WithArchiveTransaction(op, "p", func(tx *control.ArchiveTransaction) error {
		return tx.FinishMigration(func(control.ArchiveState) error { return nil })
	}); e != nil {
		t.Fatal(e)
	}
	return d, dir, op
}
func TestSummaryActivationSurvivesRestart(t *testing.T) {
	d, dir, op := summaryControl(t)
	defer func() { d.Close() }()
	before := time.Now().UTC()
	epoch, e := d.SetConsent(op, "p", "synthetic", "summary", true)
	if e != nil {
		t.Fatal(e)
	}
	got, ok, e := d.SummaryActivation("p", "synthetic")
	if e != nil || !ok || epoch != 1 || got.Project != "p" || got.Provider != "synthetic" || got.Generation != "g" || got.Ordinal != 0 || got.ConsentEpoch != 1 || got.At.Before(before) || got.At.After(time.Now().UTC()) {
		t.Fatalf("invalid baseline: %+v %v", got, e)
	}
	if e = d.Close(); e != nil {
		t.Fatal(e)
	}
	d, e = control.Open(dir)
	if e != nil {
		t.Fatal(e)
	}
	again, ok, e := d.SummaryActivation("p", "synthetic")
	if e != nil || !ok || !reflect.DeepEqual(got, again) {
		t.Fatalf("baseline lost across restart: %+v %v", again, e)
	}
	c := d.Registry().ConsentEpoch("p", "synthetic", "summary")
	if !c.Enabled || c.Epoch != epoch {
		t.Fatal("summary consent lost")
	}
	if _, ok, e = d.SummaryActivation("p", "foreign"); e != nil || ok {
		t.Fatal("foreign provider activation leaked")
	}
}

func TestSummaryRevokeRegrantUsesNewCommittedBaseline(t *testing.T) {
	d, dir, op := summaryControl(t)
	defer d.Close()
	if _, e := d.SetConsent(op, "p", "synthetic", "summary", true); e != nil {
		t.Fatal(e)
	}
	first, _, _ := d.SummaryActivation("p", "synthetic")
	epoch, e := d.SetConsent(op, "p", "synthetic", "summary", false)
	if e != nil || epoch != 2 {
		t.Fatal(epoch, e)
	}
	c := d.Registry().ConsentEpoch("p", "synthetic", "summary")
	if c.Enabled || c.RevokedThrough != 2 {
		t.Fatal("revocation cutoff not retained", c)
	}
	if e = d.WithArchiveTransaction(op, "p", func(tx *control.ArchiveTransaction) error {
		r := archive.Record{Project: "p", Provider: "synthetic", SourceInstance: "src", SessionID: "s", MessageID: "late", Type: archive.TypeMessage, Role: "user", Text: "fixture", ConsentEpoch: 1}
		if _, e := tx.Reserve(r, nil, false); e != nil {
			return e
		}
		return tx.Complete(r, func(archive.Envelope) error { return nil }, func() error { return nil })
	}); e != nil {
		t.Fatal(e)
	}
	epoch, e = d.SetConsent(op, "p", "synthetic", "summary", true)
	if e != nil || epoch != 3 {
		t.Fatal(epoch, e)
	}
	next, _, e := d.SummaryActivation("p", "synthetic")
	if e != nil || next.Ordinal != 1 || next.ConsentEpoch != 3 || next.At.Before(first.At) {
		t.Fatal(next, e)
	}
	if e = d.Close(); e != nil {
		t.Fatal(e)
	}
	again, e := control.Open(dir)
	if e != nil {
		t.Fatal(e)
	}
	defer again.Close()
	got, ok, e := again.SummaryActivation("p", "synthetic")
	if e != nil || !ok || !reflect.DeepEqual(got, next) {
		t.Fatal("new baseline lost", got, e)
	}
	if c = again.Registry().ConsentEpoch("p", "synthetic", "summary"); !c.Enabled || c.Epoch != 3 || c.RevokedThrough != 2 {
		t.Fatal("regrant resurrected revoked epoch", c)
	}
}
func TestSummaryConsentRefusesInvalidActivationWithoutPoison(t *testing.T) {
	d, dir, op := summaryControl(t)
	defer d.Close()
	for _, tc := range []struct {
		actor             registry.Principal
		project, provider string
	}{
		{registry.Principal{Kind: registry.Agent}, "p", "synthetic"}, {op, "foreign", "synthetic"}, {op, "p", ""}, {op, "p", string([]byte{255})}, {op, "p", strings.Repeat("x", 257)},
	} {
		if _, e := d.SetConsent(tc.actor, tc.project, tc.provider, "summary", true); e == nil {
			t.Fatal("invalid activation accepted")
		}
	}
	if e := d.Close(); e != nil {
		t.Fatal(e)
	}
	again, e := control.Open(dir)
	if e != nil {
		t.Fatal(e)
	}
	defer again.Close()
	if blocked, reason := again.Blocked(); blocked {
		t.Fatal("invalid request poisoned replay", reason)
	}
	if c := again.Registry().ConsentEpoch("p", "synthetic", "summary"); c.Epoch != 0 || c.Enabled {
		t.Fatal("invalid activation exposed authority")
	}
}
func TestSummaryConsentRequiresMigrationAndNoPendingArchive(t *testing.T) {
	dir := t.TempDir()
	d, e := control.Initialize(dir)
	if e != nil {
		t.Fatal(e)
	}
	defer d.Close()
	op := registry.Principal{Kind: registry.Operator}
	if e = d.MintProject(op, "p", "fixture"); e != nil {
		t.Fatal(e)
	}
	if _, e = d.SetConsent(op, "p", "synthetic", "summary", true); e == nil {
		t.Fatal("missing metadata baseline accepted")
	}
	if _, e = d.SetConsent(op, "p", "synthetic", "summary", false); e != nil {
		t.Fatal("preactivation revoke refused", e)
	}
	if e = d.BeginArchiveMigration(op, "p", "g"); e != nil {
		t.Fatal(e)
	}
	attachArchiveLedger(t, d, dir)
	if _, e = d.SetConsent(op, "p", "synthetic", "summary", true); e == nil {
		t.Fatal("incomplete migration accepted")
	}
	if e = d.WithArchiveTransaction(op, "p", func(tx *control.ArchiveTransaction) error {
		return tx.FinishMigration(func(control.ArchiveState) error { return nil })
	}); e != nil {
		t.Fatal(e)
	}
	if e = d.WithArchiveTransaction(op, "p", func(tx *control.ArchiveTransaction) error {
		_, e := tx.Reserve(archive.Record{Project: "p", SessionID: "s", MessageID: "pending"}, nil, false)
		return e
	}); e != nil {
		t.Fatal(e)
	}
	if _, e = d.SetConsent(op, "p", "synthetic", "summary", true); e == nil {
		t.Fatal("pending source accepted as complete baseline")
	}
	if c := d.Registry().ConsentEpoch("p", "synthetic", "summary"); c.Enabled || c.Epoch != 1 {
		t.Fatal("refusal changed consent", c)
	}
}
func TestSummaryConsentPersistenceOrderingAndFailure(t *testing.T) {
	for _, enable := range []bool{true, false} {
		t.Run(fmt.Sprint(enable), func(t *testing.T) {
			d, _, op := summaryControl(t)
			defer d.Close()
			if !enable {
				if _, e := d.SetConsent(op, "p", "synthetic", "summary", true); e != nil {
					t.Fatal(e)
				}
			}
			entered, release, done := make(chan struct{}), make(chan struct{}), make(chan error, 1)
			d.SetCapacityCheck(func(int64) error { close(entered); <-release; return errors.New("synthetic capacity refusal") })
			go func() { _, e := d.SetConsent(op, "p", "synthetic", "summary", enable); done <- e }()
			select {
			case <-entered:
			case <-time.After(3 * time.Second):
				close(release)
				t.Fatal("persistence hook not reached")
			}
			c := d.Registry().ConsentEpoch("p", "synthetic", "summary")
			denied := !c.Enabled
			close(release)
			e := <-done
			if !denied || e == nil {
				t.Fatal("grant-before-persist or revoke-after-persist", c, e)
			}
			if blocked, _ := d.Blocked(); !blocked {
				t.Fatal("failed persistence did not fail closed")
			}
		})
	}
}

func TestSummaryWitnessRefusedByActualOldOperator(t *testing.T) {
	old := os.Getenv("SUMMARY_OLD_OPERATOR")
	if old == "" {
		t.Skip("SUMMARY_OLD_OPERATOR absent: actual old-reader refusal NOT_TESTED")
	}
	d, dir, op := summaryControl(t)
	if e := d.Close(); e != nil {
		t.Fatal(e)
	}
	run := func() ([]byte, error) {
		ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
		defer cancel()
		cmd := exec.CommandContext(ctx, old, "-state", dir)
		// The baseline status command retains decoder EOF; use an existing successful
		// synthetic revoke operation as the old-reader positive control instead.
		cmd.Stdin = strings.NewReader(`{"Operation":"consent","Project":"p","Provider":"old-reader-probe","Capability":"capture","Enabled":false}`)
		out, e := cmd.CombinedOutput()
		if ctx.Err() != nil {
			t.Fatal("old operator timed out")
		}
		return out, e
	}
	out, e := run()
	if e != nil || !strings.Contains(string(out), `"status":"applied"`) {
		t.Fatalf("old binary positive control failed: %s %v", out, e)
	}
	d, e = control.Open(dir)
	if e != nil {
		t.Fatal(e)
	}
	attachArchiveLedger(t, d, dir)
	if _, e = d.SetConsent(op, "p", "synthetic", "summary", true); e != nil {
		d.Close()
		t.Fatal(e)
	}
	if e = d.Close(); e != nil {
		t.Fatal(e)
	}
	out, e = run()
	if e == nil || !strings.Contains(string(out), `unknown mutation kind "summary_consent_v1"`) {
		t.Fatalf("old reader did not refuse new retained witness: %s %v", out, e)
	}
	if _, e = os.Stat(filepath.Join(dir, "ingest")); !os.IsNotExist(e) {
		t.Fatal("refusal depends on intake records", e)
	}
	again, e := control.Open(dir)
	if e != nil {
		t.Fatal("new reader cannot recover", e)
	}
	defer again.Close()
	if c := again.Registry().ConsentEpoch("p", "synthetic", "summary"); !c.Enabled || c.Epoch != 1 {
		t.Fatal("old attempt changed consent", c)
	}
}
func TestSummaryBaselineSerializesWithArchiveCommit(t *testing.T) {
	d, _, op := summaryControl(t)
	defer d.Close()
	entered, release, finished := make(chan struct{}), make(chan struct{}), make(chan error, 1)
	go func() {
		finished <- d.WithArchiveTransaction(op, "p", func(tx *control.ArchiveTransaction) error {
			close(entered)
			<-release
			r := archive.Record{Project: "p", Provider: "synthetic", SourceInstance: "src", SessionID: "s", MessageID: "concurrent", Text: "fixture", ConsentEpoch: 1}
			if _, e := tx.Reserve(r, nil, false); e != nil {
				return e
			}
			return tx.Complete(r, func(archive.Envelope) error { return nil }, func() error { return nil })
		})
	}()
	<-entered
	started, consentDone := make(chan struct{}), make(chan error, 1)
	go func() { close(started); _, e := d.SetConsent(op, "p", "synthetic", "summary", true); consentDone <- e }()
	<-started
	select {
	case e := <-consentDone:
		close(release)
		<-finished
		t.Fatalf("consent overtook held archive writer: %v", e)
	case <-time.After(100 * time.Millisecond):
	}
	close(release)
	if e := <-finished; e != nil {
		t.Fatal(e)
	}
	if e := <-consentDone; e != nil {
		t.Fatal(e)
	}
	a, ok, e := d.SummaryActivation("p", "synthetic")
	if e != nil || !ok || a.Ordinal != 1 {
		t.Fatal("partial commit baseline", a, e)
	}
}

func TestSummaryReplayRejectsMalformedAndUnwitnessedConsent(t *testing.T) {
	for _, name := range []string{"valid", "legacy-enable", "generation", "ordinal", "epoch", "baseline-epoch", "provider", "zero-time", "missing-activation", "negative-epoch", "terminal-enable", "terminal-activation", "jumping-epoch", "legacy-revoke", "capability", "missing-proof", "activation-project", "bound-provider", "utc-overflow"} {
		t.Run(name, func(t *testing.T) {
			d, dir, _ := summaryControl(t)
			if e := d.Close(); e != nil {
				t.Fatal(e)
			}
			a := map[string]any{"project": "p", "provider": "synthetic", "generation": "g", "ordinal": 0, "at": "2026-01-01T00:00:00Z", "consent_epoch": 1}
			proof := map[string]any{"epoch": 1, "activation": a}
			m := map[string]any{"kind": "summary_consent_v1", "project": "p", "provider": "synthetic", "capability": "summary", "enabled": true, "summary_consent": proof}
			switch name {
			case "capability":
				m["capability"] = "capture"
			case "missing-proof":
				delete(m, "summary_consent")
			case "activation-project":
				a["project"] = "foreign"
			case "bound-provider":
				m["provider"] = strings.Repeat("x", 257)
				a["provider"] = m["provider"]
			case "utc-overflow":
				a["at"] = "9999-12-31T23:59:59-01:00"
			case "terminal-activation":
				m["enabled"] = false
				proof["terminal"] = true
			case "jumping-epoch":
				proof["epoch"] = 2
				a["consent_epoch"] = 2
			case "terminal-enable":
				proof["terminal"] = true
			case "legacy-revoke":
				m["kind"] = "set_consent"
				m["enabled"] = false
				delete(m, "summary_consent")
			case "legacy-enable":
				m["kind"] = "set_consent"
				delete(m, "summary_consent")
			case "generation":
				a["generation"] = "foreign"
			case "ordinal":
				a["ordinal"] = 1
			case "epoch":
				proof["epoch"] = 2
			case "baseline-epoch":
				a["consent_epoch"] = 2
			case "provider":
				a["provider"] = "foreign"
			case "zero-time":
				a["at"] = "0001-01-01T00:00:00Z"
			case "missing-activation":
				delete(proof, "activation")
			case "negative-epoch":
				proof["epoch"] = -1
			}
			raw, e := json.Marshal(m)
			if e != nil {
				t.Fatal(e)
			}
			w, e := wal.Open(filepath.Join(dir, "wal"))
			if e != nil {
				t.Fatal(e)
			}
			if _, e = w.Accept("synthetic-summary-replay", raw); e != nil {
				w.Close()
				t.Fatal(e)
			}
			if e = w.Close(); e != nil {
				t.Fatal(e)
			}
			got, e := control.Open(dir)
			if name == "valid" || name == "legacy-revoke" {
				if e != nil {
					t.Fatal("valid retained transition refused", e)
				}
				defer got.Close()
				if c := got.Registry().ConsentEpoch("p", "synthetic", "summary"); c.Enabled != (name == "valid") || c.Epoch != 1 {
					t.Fatal("valid replay lost consent", c)
				}
			} else {
				if e != nil && !strings.Contains(e.Error(), "invalid summary consent or activation") {
					t.Fatal("unrelated error is not strict replay refusal", e)
				}
				if e == nil {
					blocked, _ := got.Blocked()
					got.Close()
					if !blocked {
						t.Fatal("invalid replay exposed authority")
					}
				}
			}
		})
	}
}

func TestSummaryReplayTerminalRevokeStaysBlocked(t *testing.T) {
	d, dir, _ := summaryControl(t)
	if e := d.Close(); e != nil {
		t.Fatal(e)
	}
	w, e := wal.Open(filepath.Join(dir, "wal"))
	if e != nil {
		t.Fatal(e)
	}
	raw := []byte(`{"kind":"summary_consent_v1","project":"p","provider":"synthetic","capability":"summary","enabled":false,"summary_consent":{"epoch":1,"terminal":true}}`)
	if _, e = w.Accept("synthetic-terminal-revoke", raw); e != nil {
		w.Close()
		t.Fatal(e)
	}
	w.Close()
	got, e := control.Open(dir)
	if e != nil && !errors.Is(e, control.ErrSummaryTerminal) {
		t.Fatal("unrelated failure is not terminal refusal", e)
	}
	if e == nil {
		blocked, _ := got.Blocked()
		got.Close()
		if !blocked {
			t.Fatal("terminal revocation witness reopened serving authority")
		}
	}
}

func TestSummaryRequiresReadyLedgerAndExplicitReenable(t *testing.T) {
	d, dir, op := summaryControl(t)
	d.Close()
	var e error
	d, e = control.Open(dir)
	if e != nil {
		t.Fatal(e)
	}
	defer d.Close()
	if _, e = d.SetConsent(op, "p", "synthetic", "summary", true); e == nil {
		t.Fatal("enabled without live accounting")
	}
	attachArchiveLedger(t, d, dir)
	if e = d.WithStableAuthority(op, func(*registry.Registry) error {
		return d.ReserveIdentifiedExternal(budget.Evidence{Kind: "fixture", KeyHash: "pending"}, 1)
	}); e != nil {
		t.Fatal(e)
	}
	if _, e = d.SetConsent(op, "p", "synthetic", "summary", true); e == nil {
		t.Fatal("pending intent ignored")
	}
	if e = d.WithStableAuthority(op, func(*registry.Registry) error {
		if e := d.ReserveIdentifiedExternal(budget.Evidence{Kind: "fixture", KeyHash: "pending"}, 0); e != nil {
			return e
		}
		return d.FinishExternal()
	}); e != nil {
		t.Fatal(e)
	}
	for _, want := range []int64{1, 2} {
		epoch, e := d.SetConsent(op, "p", "synthetic", "summary", true)
		if e != nil || epoch != want {
			t.Fatal(epoch, e)
		}
		a, ok, e := d.SummaryActivation("p", "synthetic")
		if e != nil || !ok || a.ConsentEpoch != want || a.Ordinal != 0 {
			t.Fatal("re-enable reused old activation", a, e)
		}
	}
}

func TestSummaryDurableWitnessSurvivesMarkerFailure(t *testing.T) {
	for _, enable := range []bool{true, false} {
		t.Run(fmt.Sprint(enable), func(t *testing.T) {
			d, dir, op := summaryControl(t)
			defer func() { d.Close() }()
			if !enable {
				if _, e := d.SetConsent(op, "p", "synthetic", "summary", true); e != nil {
					t.Fatal(e)
				}
			}
			staging := filepath.Join(dir, "control.meta.tmp")
			if e := os.Mkdir(staging, 0700); e != nil {
				t.Fatal(e)
			}
			if _, e := d.SetConsent(op, "p", "synthetic", "summary", enable); !errors.Is(e, control.ErrPersistence) {
				t.Fatal("uncertain accept not surfaced", e)
			}
			if blocked, _ := d.Blocked(); !blocked {
				t.Fatal("uncertain live authority exposed")
			}
			d.Close()
			if e := os.Remove(staging); e != nil {
				t.Fatal(e)
			}
			var e error
			d, e = control.Open(dir)
			if e != nil {
				t.Fatal(e)
			}
			attachArchiveLedger(t, d, dir)
			want := int64(1)
			if !enable {
				want = 2
			}
			c := d.Registry().ConsentEpoch("p", "synthetic", "summary")
			if c.Epoch != want || c.Enabled != enable || (!enable && c.RevokedThrough != 2) {
				t.Fatal("accepted witness lost or applied twice", c)
			}
			a, ok, e := d.SummaryActivation("p", "synthetic")
			if e != nil || !ok || a.ConsentEpoch != 1 || a.Ordinal != 0 {
				t.Fatal("durable activation lost", a, e)
			}
			d.Close()
			d, e = control.Open(dir)
			if e != nil {
				t.Fatal(e)
			}
			again, ok, e := d.SummaryActivation("p", "synthetic")
			if e != nil || !ok || !reflect.DeepEqual(a, again) || d.Registry().ConsentEpoch("p", "synthetic", "summary").Epoch != want {
				t.Fatal("reopen changed accepted transition", again, e)
			}
		})
	}
}

func TestSummaryReplayRequiresCompletedMigration(t *testing.T) {
	dir := t.TempDir()
	d, e := control.Initialize(dir)
	if e != nil {
		t.Fatal(e)
	}
	op := registry.Principal{Kind: registry.Operator}
	if e = d.MintProject(op, "p", "fixture"); e != nil {
		d.Close()
		t.Fatal(e)
	}
	if e = d.BeginArchiveMigration(op, "p", "g"); e != nil {
		d.Close()
		t.Fatal(e)
	}
	d.Close()
	w, e := wal.Open(filepath.Join(dir, "wal"))
	if e != nil {
		t.Fatal(e)
	}
	payload := []byte(`{"kind":"summary_consent_v1","project":"p","provider":"synthetic","capability":"summary","enabled":true,"summary_consent":{"epoch":1,"activation":{"project":"p","provider":"synthetic","generation":"g","ordinal":0,"at":"2026-01-01T00:00:00Z","consent_epoch":1}}}`)
	if _, e = w.Accept("synthetic-incomplete-migration", payload); e != nil {
		w.Close()
		t.Fatal(e)
	}
	w.Close()
	got, e := control.Open(dir)
	if got != nil {
		got.Close()
	}
	if e == nil || !strings.Contains(e.Error(), "invalid summary consent or activation") {
		t.Fatal("unready migration replay acknowledged", e)
	}
}

func TestSummaryActivationGetterDeniesBlockedAuthority(t *testing.T) {
	d, _, op := summaryControl(t)
	defer d.Close()
	if _, e := d.SetConsent(op, "p", "synthetic", "summary", true); e != nil {
		t.Fatal(e)
	}
	a, _, _ := d.SummaryActivation("p", "synthetic")
	a.Project = "foreign"
	if b, _, e := d.SummaryActivation("p", "synthetic"); e != nil || b.Project != "p" {
		t.Fatal("getter retained mutable returned baseline", b, e)
	}
	d.SetCapacityCheck(func(int64) error { return errors.New("synthetic refusal") })
	if _, e := d.SetConsent(op, "p", "synthetic", "summary", true); e == nil {
		t.Fatal("fault not reached")
	}
	if a, ok, e := d.SummaryActivation("p", "synthetic"); !errors.Is(e, control.ErrBlocked) || ok || a.Project != "" {
		t.Fatal("blocked getter exposed stale baseline", a, e)
	}
}
func TestSummaryReplayRefusesPendingArchiveOperation(t *testing.T) {
	d, dir, op := summaryControl(t)
	if e := d.WithArchiveTransaction(op, "p", func(tx *control.ArchiveTransaction) error {
		_, e := tx.Reserve(archive.Record{Project: "p", SourceInstance: "i", SessionID: "s", MessageID: "pending"}, nil, false)
		return e
	}); e != nil {
		d.Close()
		t.Fatal(e)
	}
	d.Close()
	w, e := wal.Open(filepath.Join(dir, "wal"))
	if e != nil {
		t.Fatal(e)
	}
	raw := []byte(`{"kind":"summary_consent_v1","project":"p","provider":"synthetic","capability":"summary","enabled":true,"summary_consent":{"epoch":1,"activation":{"project":"p","provider":"synthetic","generation":"g","ordinal":0,"at":"2026-01-01T00:00:00Z","consent_epoch":1}}}`)
	if _, e = w.Accept("synthetic-invalid-pending-grant", raw); e != nil {
		w.Close()
		t.Fatal(e)
	}
	w.Close()
	got, e := control.Open(dir)
	if got != nil {
		got.Close()
	}
	if e == nil || !strings.Contains(e.Error(), "invalid summary consent or activation") {
		t.Fatal("grant overtook pending source on replay", e)
	}
}
