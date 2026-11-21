package control

import (
	"reflect"
	"testing"
	"time"
)

func TestSummaryInitialKindRejectsNonInitialStatesBeforeMutation(t *testing.T) {
	for _, name := range []string{"valid", "enabled", "revoked", "prior-activation", "disable", "terminal", "epoch"} {
		t.Run(name, func(t *testing.T) {
			d := mustInit(t, t.TempDir())
			defer d.Close()
			if err := d.MintProject(operator(), "p", "fixture"); err != nil {
				t.Fatal(err)
			}
			d.archiveStates = map[string]ArchiveState{"p": {Generation: "g", Version: 2, MigrationComplete: true, NextOrdinal: 1}}
			a := SummaryActivation{Project: "p", Provider: "synthetic", Generation: "g", At: time.Now().UTC(), ConsentEpoch: 1}
			m := mutation{Kind: kSummaryInitialConsent, Project: "p", Provider: "synthetic", Capability: "summary", Enabled: true, SummaryConsent: &summaryConsentMutation{Epoch: 1, Activation: &a}}
			switch name {
			case "enabled":
				d.reg.SetConsent(operator(), "p", "synthetic", "summary", true)
			case "revoked":
				d.reg.SetConsent(operator(), "p", "synthetic", "summary", false)
			case "prior-activation":
				d.summaryActivations = map[summaryScope]SummaryActivation{{"p", "synthetic"}: a}
			case "disable":
				m.Enabled = false
			case "terminal":
				m.SummaryConsent.Terminal = true
			case "epoch":
				m.SummaryConsent.Epoch = 2
				a.ConsentEpoch = 2
			}
			before := d.reg.ConsentEpoch("p", "synthetic", "summary")
			state := d.archiveStates["p"]
			activation, had := d.summaryActivations[summaryScope{"p", "synthetic"}]
			err := d.applySummaryConsent(m)
			if name == "valid" {
				if err != nil || d.archiveStates["p"].PolicyRevision != state.PolicyRevision {
					t.Fatal("valid initial kind rejected or invalidated originals", err)
				}
				return
			}
			got, found := d.summaryActivations[summaryScope{"p", "synthetic"}]
			if err == nil || d.reg.ConsentEpoch("p", "synthetic", "summary") != before || !reflect.DeepEqual(d.archiveStates["p"], state) || got != activation || found != had {
				t.Fatal("malformed initial witness mutated authority", name, err)
			}
		})
	}
}
