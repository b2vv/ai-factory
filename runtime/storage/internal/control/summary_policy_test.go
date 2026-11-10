package control_test

import (
	"aifactory.local/storage/internal/archive"
	"aifactory.local/storage/internal/control"
	"aifactory.local/storage/internal/registry"
	"testing"
	"time"
)

func TestSummaryPolicyRechecksCurrentConsentAndAllCoveredRecords(t *testing.T) {
	d, _, op := summaryControl(t)
	defer d.Close()
	if _, err := d.SetConsent(op, "p", "synthetic", "capture", true); err != nil {
		t.Fatal(err)
	}
	if _, err := d.SetConsent(op, "p", "synthetic", "summary", true); err != nil {
		t.Fatal(err)
	}
	activation, found, err := d.SummaryActivation("p", "synthetic")
	if err != nil || !found {
		t.Fatal(err)
	}
	summary := archive.Record{Project: "p", Provider: "synthetic", SourceInstance: "i", SessionID: "s", MessageID: "extract", Type: archive.TypeSummary, Role: "assistant", ConsentEpoch: 1}
	original := summary
	original.MessageID = "source"
	original.Type = archive.TypeMessage
	original.Role = "user"
	check := func(want bool, a control.SummaryActivation, records []archive.Record) {
		t.Helper()
		err := d.WithArchiveTransaction(op, "p", func(tx *control.ArchiveTransaction) error {
			allowed, err := tx.SummaryPolicyAllows(a, records)
			if err != nil || allowed != want {
				t.Fatal("summary policy", allowed, err, "want", want)
			}
			return nil
		})
		if err != nil {
			t.Fatal(err)
		}
	}
	check(true, activation, []archive.Record{summary, original})
	original.Edited = true
	check(true, activation, []archive.Record{summary, original})
	original.Edited = false
	original.ConsentEpoch = 2
	check(false, activation, []archive.Record{summary, original})
	original.ConsentEpoch = 1
	original.Provider = "other"
	check(false, activation, []archive.Record{summary, original})
	original.Provider = "synthetic"
	if _, err := d.SetConsent(op, "p", "synthetic", "summary", false); err != nil {
		t.Fatal(err)
	}
	check(false, activation, []archive.Record{summary, original})
	if _, err := d.SetConsent(op, "p", "synthetic", "summary", true); err != nil {
		t.Fatal(err)
	}
	check(false, activation, []archive.Record{summary, original})
	activation, _, err = d.SummaryActivation("p", "synthetic")
	if err != nil {
		t.Fatal(err)
	}
	check(true, activation, []archive.Record{summary, original})
	if _, err := d.SetConsent(op, "p", "synthetic", "capture", false); err != nil {
		t.Fatal(err)
	}
	check(false, activation, []archive.Record{summary, original})
}

func TestSummaryPolicyRejectsChangedAuthorityAndUnservableSources(t *testing.T) {
	cases := []struct {
		name   string
		mutate func(*control.SummaryActivation, *[]archive.Record)
		setup  func(*control.Durable, registry.Principal) error
	}{
		{name: "activation-frontier", mutate: func(a *control.SummaryActivation, _ *[]archive.Record) { a.Ordinal++ }},
		{name: "activation-time", mutate: func(a *control.SummaryActivation, _ *[]archive.Record) { a.At = a.At.Add(time.Nanosecond) }},
		{name: "missing-covered-original", mutate: func(_ *control.SummaryActivation, r *[]archive.Record) { *r = (*r)[:1] }},
		{name: "foreign-original-project", mutate: func(_ *control.SummaryActivation, r *[]archive.Record) { (*r)[1].Project = "foreign" }},
		{name: "withdrawn-original", mutate: func(_ *control.SummaryActivation, r *[]archive.Record) { (*r)[1].Withdrawn = true }},
		{name: "withdrawn-derived", mutate: func(_ *control.SummaryActivation, r *[]archive.Record) { (*r)[0].Withdrawn = true }},
		{name: "derived-type", mutate: func(_ *control.SummaryActivation, r *[]archive.Record) { (*r)[0].Type = archive.TypeMessage }},
		{name: "original-type", mutate: func(_ *control.SummaryActivation, r *[]archive.Record) { (*r)[1].Type = archive.TypeSummary }},
		{name: "project-retention", setup: func(d *control.Durable, op registry.Principal) error {
			_, err := d.DeleteProjectBarrier(op, "p")
			return err
		}},
		{name: "source-session-retention", setup: func(d *control.Durable, op registry.Principal) error {
			_, err := d.DeleteSessionBarrier(op, "p", "source-session")
			return err
		}},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			d, _, op := summaryControl(t)
			defer d.Close()
			for _, purpose := range []string{"capture", "summary"} {
				if _, err := d.SetConsent(op, "p", "synthetic", purpose, true); err != nil {
					t.Fatal(err)
				}
			}
			a, found, err := d.SummaryActivation("p", "synthetic")
			if err != nil || !found {
				t.Fatal(err)
			}
			records := []archive.Record{{Project: "p", Provider: "synthetic", SourceInstance: "i", SessionID: "derived-session", MessageID: "extract", Type: archive.TypeSummary, Role: "assistant", ConsentEpoch: 1}, {Project: "p", Provider: "synthetic", SourceInstance: "i", SessionID: "source-session", MessageID: "original", Type: archive.TypeMessage, Role: "user", ConsentEpoch: 1}}
			if tc.setup != nil {
				if err = tc.setup(d, op); err != nil {
					t.Fatal(err)
				}
			}
			if tc.mutate != nil {
				tc.mutate(&a, &records)
			}
			if err = d.WithArchiveTransaction(op, "p", func(tx *control.ArchiveTransaction) error {
				allowed, err := tx.SummaryPolicyAllows(a, records)
				if err != nil || allowed {
					t.Fatal("invalid authority/source served", allowed, err)
				}
				return nil
			}); err != nil {
				t.Fatal(err)
			}
		})
	}
}
