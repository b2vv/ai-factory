package summary

import (
	"aifactory.local/storage/internal/archive"
	"strings"
	"testing"
	"time"
)

func TestAcceptedHeadProgressStartsOnlyNewOriginals(t *testing.T) {
	in := exampleInput()
	old := in.Messages[0]
	next := old
	next.Metadata.Ordinal = 2
	next.Record.MessageID = "m2"
	next.Record.Text = "new original"
	in.Messages = []archive.Envelope{old, next}
	in.Cutoff = 2
	in.Progress = &Progress{AfterOrdinal: 1, PreviousJobID: strings.Repeat("a", 64)}
	now := old.Metadata.CapturedAt.Add(30 * time.Minute)
	d, e := Plan(DefaultConfig(), now, in)
	if e != nil || !d.Ready || len(d.Selected) != 1 || d.Selected[0].Record.MessageID != "m2" || d.Manifest.Progress == nil || d.Manifest.Progress.AfterOrdinal != 1 {
		t.Fatal("head frontier lost", d, e)
	}
	firstKey := d.JobID
	in.Progress.PreviousJobID = strings.Repeat("b", 64)
	if d.Manifest.Progress.PreviousJobID != strings.Repeat("a", 64) {
		t.Fatal("returned proof aliases mutable caller progress")
	}
	other, e := Plan(DefaultConfig(), now, in)
	if e != nil || other.JobID == firstKey {
		t.Fatal("previous head not bound to processing identity", e)
	}
}

func TestProgressRejectsUnprovedOrOutOfRangeFrontiers(t *testing.T) {
	for _, p := range []Progress{{0, strings.Repeat("a", 64)}, {2, strings.Repeat("a", 64)}, {1, "short"}, {1, strings.Repeat("a", 62)}, {1, strings.Repeat("g", 64)}} {
		in := exampleInput()
		in.Progress = &p
		now := in.Messages[0].Metadata.CapturedAt.Add(15 * time.Minute)
		if _, err := Plan(DefaultConfig(), now, in); err == nil {
			t.Fatal("unproved progress accepted", p)
		}
	}
}
