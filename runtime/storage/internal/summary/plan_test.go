package summary

import (
	"aifactory.local/storage/internal/archive"
	"encoding/json"
	"strings"
	"testing"
	"time"
)

func exampleInput() Input {
	start := time.Date(2026, 11, 10, 9, 0, 0, 0, time.UTC)
	return Input{Scope: Scope{Project: "p", Provider: "synthetic", SourceInstance: "i", SessionID: "s"}, Generation: "g", Cutoff: 1, Complete: true, Activation: &Baseline{Project: "p", Generation: "g", Ordinal: 0, At: start.Add(-time.Second)}, GeneratorVersion: "extractive/1", Messages: []archive.Envelope{{Version: 2, Record: archive.Record{Project: "p", Provider: "synthetic", SourceInstance: "i", SessionID: "s", MessageID: "m1", Type: archive.TypeMessage, Role: "user", Text: "A concrete source statement", ConsentEpoch: 1}, Metadata: archive.Metadata{Generation: "g", Ordinal: 1, CapturedAt: &start}}}}
}
func TestIdleDeadlineIsInclusive(t *testing.T) {
	in := exampleInput()
	start := *in.Messages[0].Metadata.CapturedAt
	before, err := Plan(DefaultConfig(), start.Add(15*time.Minute-time.Nanosecond), in)
	if err != nil || before.Ready || before.NextDue == nil || !before.NextDue.Equal(start.Add(15*time.Minute)) {
		t.Fatalf("before deadline: %+v %v", before, err)
	}
	due, err := Plan(DefaultConfig(), start.Add(15*time.Minute), in)
	if err != nil || !due.Ready || due.Reason != "idle" || len(due.Selected) != 1 || due.JobID == "" {
		t.Fatalf("at deadline: %+v %v", due, err)
	}
}

func TestPlanRejectsUnverifiedInputs(t *testing.T) {
	start := *exampleInput().Messages[0].Metadata.CapturedAt
	cases := []struct {
		name   string
		change func(*Input, *Config)
	}{
		{"missing activation", func(i *Input, c *Config) { i.Activation = nil }},
		{"wrong activation generation", func(i *Input, c *Config) { i.Activation.Generation = "old" }},
		{"baseline beyond cutoff", func(i *Input, c *Config) { i.Activation.Ordinal = 2 }},
		{"foreign record", func(i *Input, c *Config) { i.Messages[0].Record.Project = "other" }},
		{"foreign provider", func(i *Input, c *Config) { i.Messages[0].Record.Provider = "other" }},
		{"wrong generation", func(i *Input, c *Config) { i.Messages[0].Metadata.Generation = "old" }},
		{"beyond cutoff", func(i *Input, c *Config) { i.Messages[0].Metadata.Ordinal = 2 }},
		{"missing source time", func(i *Input, c *Config) { i.Messages[0].Metadata.CapturedAt = nil }},
		{"future source", func(i *Input, c *Config) { v := start.Add(time.Hour); i.Messages[0].Metadata.CapturedAt = &v }},
		{"empty source id", func(i *Input, c *Config) { i.Messages[0].Record.MessageID = "" }},
		{"unknown branch named", func(i *Input, c *Config) { i.Scope.Branch = "invented" }},
		{"invalid duration", func(i *Input, c *Config) { c.IdleAfter = 0 }},
		{"invalid byte budget", func(i *Input, c *Config) { c.MaxInputBytes = 0 }},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			in := exampleInput()
			c := DefaultConfig()
			tc.change(&in, &c)
			if _, err := Plan(c, start.Add(15*time.Minute), in); err == nil {
				t.Fatal("unverified input accepted")
			}
		})
	}
}

func TestCanonicalRetriesAndOrdinalConflicts(t *testing.T) {
	in := exampleInput()
	now := in.Messages[0].Metadata.CapturedAt.Add(15 * time.Minute)
	in.Messages = append(in.Messages, in.Messages[0])
	d, err := Plan(DefaultConfig(), now, in)
	if err != nil || len(d.Selected) != 1 {
		t.Fatalf("exact retry must collapse: %d %v", len(d.Selected), err)
	}
	cases := []struct {
		name   string
		change func(*archive.Envelope)
	}{
		{"payload", func(e *archive.Envelope) { e.Record.Text = "different payload" }},
		{"capture time", func(e *archive.Envelope) { v := e.Metadata.CapturedAt.Add(time.Second); e.Metadata.CapturedAt = &v }},
		{"ordinal reused", func(e *archive.Envelope) { e.Record.MessageID = "m2" }},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			in := exampleInput()
			other := in.Messages[0]
			tc.change(&other)
			in.Messages = append(in.Messages, other)
			if _, err := Plan(DefaultConfig(), now, in); err == nil {
				t.Fatal("conflicting observation accepted")
			}
		})
	}
}
func TestJobIdentityStableAcrossOrderAndUnrelatedCutoff(t *testing.T) {
	in := exampleInput()
	e := in.Messages[0]
	e.Record.MessageID = "m2"
	e.Metadata.Ordinal = 2
	v := e.Metadata.CapturedAt.Add(10 * time.Minute)
	e.Metadata.CapturedAt = &v
	in.Messages = append(in.Messages, e)
	in.Cutoff = 2
	now := v.Add(20 * time.Minute)
	a, err := Plan(DefaultConfig(), now, in)
	if err != nil {
		t.Fatal(err)
	}
	in.Messages[0], in.Messages[1] = in.Messages[1], in.Messages[0]
	in.Cutoff = 99
	b, err := Plan(DefaultConfig(), now, in)
	if err != nil || !a.Ready || !b.Ready || a.JobID != b.JobID || b.Selected[0].Metadata.Ordinal != 1 {
		t.Fatalf("order/cutoff changed identity: %s %s %v", a.JobID, b.JobID, err)
	}
}

func TestCoveredSourcesDoNotRestartTimerButLateArrivalDoes(t *testing.T) {
	in := exampleInput()
	start := *in.Messages[0].Metadata.CapturedAt
	prior, err := Plan(DefaultConfig(), start.Add(15*time.Minute), in)
	if err != nil {
		t.Fatal(err)
	}
	in.Covered = prior.Manifest.Sources
	idle, err := Plan(DefaultConfig(), start.Add(time.Hour), in)
	if err != nil || idle.Ready || idle.Reason != "no_new_messages" {
		t.Fatalf("covered restarted timer: %+v %v", idle, err)
	}
	late := in.Messages[0]
	late.Record.MessageID = "late"
	late.Metadata.Ordinal = 2
	captured := start.Add(time.Hour)
	event := start.Add(-24 * time.Hour)
	late.Metadata.CapturedAt = &captured
	late.Metadata.SourceEventTime = &event
	in.Messages = append(in.Messages, late)
	in.Cutoff = 2
	notYet, err := Plan(DefaultConfig(), captured.Add(14*time.Minute), in)
	if err != nil || notYet.Ready {
		t.Fatalf("late event used historical time: %+v %v", notYet, err)
	}
	due, err := Plan(DefaultConfig(), captured.Add(15*time.Minute), in)
	if err != nil || !due.Ready || len(due.Selected) != 1 || due.Selected[0].Record.MessageID != "late" {
		t.Fatalf("late source skipped: %+v %v", due, err)
	}
	if due.Manifest.CaptureCompleteness != "unknown" || due.Manifest.Scope.BranchKnown {
		t.Fatal("invented completeness or branch")
	}
}
func TestStaleCoverageRequiresRevalidation(t *testing.T) {
	in := exampleInput()
	now := in.Messages[0].Metadata.CapturedAt.Add(15 * time.Minute)
	d, err := Plan(DefaultConfig(), now, in)
	if err != nil {
		t.Fatal(err)
	}
	in.Covered = d.Manifest.Sources
	in.Messages[0].Record.Text = "changed source"
	if _, err := Plan(DefaultConfig(), now, in); err == nil {
		t.Fatal("stale coverage accepted")
	}
}

func TestByteSafeguardUsesWholeRecordPrefixAndInclusiveLimit(t *testing.T) {
	in := exampleInput()
	start := *in.Messages[0].Metadata.CapturedAt
	first, _ := archive.EncodeEnvelope(in.Messages[0])
	cost := len(first) + 1
	c := DefaultConfig()
	c.MaxInputBytes = cost
	exact, err := Plan(c, start, in)
	if err != nil || !exact.Ready || exact.Reason != "size" || len(exact.Selected) != 1 {
		t.Fatalf("exact byte boundary: %+v %v", exact, err)
	}
	second := in.Messages[0]
	second.Record.MessageID = "m2"
	second.Metadata.Ordinal = 2
	in.Messages = append(in.Messages, second)
	in.Cutoff = 2
	prefix, err := Plan(c, start, in)
	if err != nil || !prefix.Ready || len(prefix.Selected) != 1 || prefix.Selected[0].Record.MessageID != "m1" || len(prefix.Manifest.Sources) != 1 {
		t.Fatalf("unsafe prefix: %+v %v", prefix, err)
	}
	c.MaxInputBytes = cost - 1
	if _, err := Plan(c, start, in); err == nil {
		t.Fatal("oversized first source silently skipped or truncated")
	}
}
func TestUnknownIncompleteAndHistoricalSourcesNeverProduceJob(t *testing.T) {
	in := exampleInput()
	now := in.Messages[0].Metadata.CapturedAt.Add(time.Hour)
	in.Complete = false
	d, err := Plan(DefaultConfig(), now, in)
	if err != nil || d.Ready || d.Reason != "incomplete" {
		t.Fatalf("partial observation: %+v %v", d, err)
	}
	in = exampleInput()
	in.Activation.Ordinal = 1
	d, err = Plan(DefaultConfig(), now, in)
	if err != nil || d.Ready {
		t.Fatalf("historical backfill: %+v %v", d, err)
	}
	in = exampleInput()
	in.Messages[0].Record.Type = archive.TypeSummary
	d, err = Plan(DefaultConfig(), now, in)
	if err != nil || d.Ready {
		t.Fatalf("summary triggered summary: %+v %v", d, err)
	}
}
func TestTimeOverflowAndClockFloorRefused(t *testing.T) {
	in := exampleInput()
	v := time.Date(9999, 12, 31, 23, 59, 59, 0, time.UTC)
	in.Messages[0].Metadata.CapturedAt = &v
	in.Activation.At = v
	if _, err := Plan(DefaultConfig(), v, in); err == nil {
		t.Fatal("unserializable due time accepted")
	}
	in = exampleInput()
	now := in.Messages[0].Metadata.CapturedAt.Add(time.Hour)
	in.ClockFloor = now.Add(time.Second)
	if _, err := Plan(DefaultConfig(), now, in); err == nil {
		t.Fatal("observed clock retreat accepted")
	}
}

func TestWithdrawnOriginalIsNeverPlanned(t *testing.T) {
	in := exampleInput()
	in.Messages[0].Record.Withdrawn = true
	if _, err := Plan(DefaultConfig(), in.Messages[0].Metadata.CapturedAt.Add(15*time.Minute), in); err == nil {
		t.Fatal("withdrawn source planned")
	}
}
func TestActiveAndIdleTie(t *testing.T) {
	for _, secondAt := range []time.Duration{15 * time.Minute, 29 * time.Minute} {
		in := exampleInput()
		first := *in.Messages[0].Metadata.CapturedAt
		e := in.Messages[0]
		e.Record.MessageID = "m2"
		e.Metadata.Ordinal = 2
		v := first.Add(secondAt)
		e.Metadata.CapturedAt = &v
		in.Messages = append(in.Messages, e)
		in.Cutoff = 2
		d, err := Plan(DefaultConfig(), first.Add(30*time.Minute), in)
		reason := "active"
		if secondAt == 15*time.Minute {
			reason = "idle"
		}
		if err != nil || !d.Ready || d.Reason != reason {
			t.Fatalf("deadline/tie: %+v %v", d, err)
		}
	}
}
func TestLegacyTimeAndReferenceBounds(t *testing.T) {
	in := exampleInput()
	now := in.Messages[0].Metadata.CapturedAt.Add(time.Hour)
	in.Messages[0].Metadata.Legacy = true
	in.Messages[0].Metadata.CapturedAt = nil
	in.Activation.Ordinal = 1
	if d, err := Plan(DefaultConfig(), now, in); err != nil || d.Ready {
		t.Fatalf("legacy historical source: %+v %v", d, err)
	}
	in.Activation.Ordinal = 0
	if _, err := Plan(DefaultConfig(), now, in); err == nil {
		t.Fatal("unknown legacy time invented")
	}
	in = exampleInput()
	c := DefaultConfig()
	c.MaxReferenceBytes = 1
	if _, err := Plan(c, now, in); err == nil {
		t.Fatal("reference budget ignored")
	}
}
func TestDecisionDoesNotMutateOriginalTimePointers(t *testing.T) {
	in := exampleInput()
	before := *in.Messages[0].Metadata.CapturedAt
	d, err := Plan(DefaultConfig(), before.Add(15*time.Minute), in)
	if err != nil {
		t.Fatal(err)
	}
	*d.Selected[0].Metadata.CapturedAt = before.Add(24 * time.Hour)
	if !in.Messages[0].Metadata.CapturedAt.Equal(before) {
		t.Fatal("planner returned source pointer alias")
	}
}

func TestEverySuppliedCaptureTimeIsChecked(t *testing.T) {
	for _, kind := range []string{"historical", "summary"} {
		t.Run(kind, func(t *testing.T) {
			in := exampleInput()
			now := *in.Messages[0].Metadata.CapturedAt
			future := now.Add(time.Hour)
			in.Messages[0].Metadata.CapturedAt = &future
			if kind == "historical" {
				in.Activation.Ordinal = 1
			} else {
				in.Messages[0].Record.Type = archive.TypeSummary
			}
			if _, err := Plan(DefaultConfig(), now, in); err == nil {
				t.Fatal("future supplied capture time accepted")
			}
		})
	}
}
func TestAdmissionRefusesBeforeLargeSerialization(t *testing.T) {
	in := exampleInput()
	now := in.Messages[0].Metadata.CapturedAt.Add(15 * time.Minute)
	c := DefaultConfig()
	c.MaxInputBytes = 512
	c.MaxObservationBytes = 1024
	large := in
	large.Messages = append([]archive.Envelope(nil), in.Messages...)
	large.Messages[0].Record.Text = string(make([]byte, 2<<20))
	for _, tc := range []struct {
		name   string
		input  Input
		config Config
	}{{"oversized envelope", large, c}} {
		t.Run(tc.name, func(t *testing.T) {
			bench := testing.Benchmark(func(b *testing.B) {
				for n := 0; n < b.N; n++ {
					if _, err := Plan(tc.config, now, tc.input); err == nil {
						b.Fatal("oversized source admitted")
					}
				}
			})
			if bench.AllocedBytesPerOp() > 128<<10 {
				t.Fatalf("admission allocated %d bytes/op before rejecting", bench.AllocedBytesPerOp())
			}
		})
	}
	prior, err := Plan(DefaultConfig(), now, in)
	if err != nil {
		t.Fatal(err)
	}
	in.Covered = make([]SourceRef, 512)
	for n := range in.Covered {
		in.Covered[n] = prior.Manifest.Sources[0]
	}
	c = DefaultConfig()
	c.MaxReferenceBytes = 1024
	bench := testing.Benchmark(func(b *testing.B) {
		for n := 0; n < b.N; n++ {
			if _, err := Plan(c, now, in); err == nil {
				b.Fatal("oversized coverage admitted")
			}
		}
	})
	if bench.AllocedBytesPerOp() > 128<<10 {
		t.Fatalf("coverage admission allocated %d bytes/op", bench.AllocedBytesPerOp())
	}
}

func TestCoverageReferenceBudgetIsInclusive(t *testing.T) {
	in := exampleInput()
	now := in.Messages[0].Metadata.CapturedAt.Add(15 * time.Minute)
	prior, err := Plan(DefaultConfig(), now, in)
	if err != nil {
		t.Fatal(err)
	}
	in.Covered = prior.Manifest.Sources
	raw, err := json.Marshal(in.Covered)
	if err != nil {
		t.Fatal(err)
	}
	c := DefaultConfig()
	c.MaxReferenceBytes = len(raw)
	d, err := Plan(c, now, in)
	if err != nil || d.Ready {
		t.Fatalf("exact coverage budget rejected: %+v %v", d, err)
	}
}

func TestArrivalClockAndOrdinalPrefixAreIndependent(t *testing.T) {
	in := exampleInput()
	start := *in.Messages[0].Metadata.CapturedAt
	e := in.Messages[0]
	e.Record.MessageID = "m2"
	e.Metadata.Ordinal = 2
	later := start.Add(10 * time.Minute)
	in.Messages[0].Metadata.CapturedAt = &later
	in.Messages = append(in.Messages, e)
	in.Cutoff = 2
	before, err := Plan(DefaultConfig(), start.Add(25*time.Minute-time.Nanosecond), in)
	if err != nil || before.Ready {
		t.Fatalf("wrong activity clock: %+v %v", before, err)
	}
	d, err := Plan(DefaultConfig(), start.Add(25*time.Minute), in)
	if err != nil || !d.Ready || d.Reason != "idle" || d.Selected[0].Record.MessageID != "m1" {
		t.Fatalf("clock/order conflated: %+v %v", d, err)
	}
}
func TestOversizedMiddleDoesNotSkipToSmallerTail(t *testing.T) {
	in := exampleInput()
	first := in.Messages[0]
	middle := first
	middle.Record.MessageID = "middle"
	middle.Metadata.Ordinal = 2
	middle.Record.Text = strings.Repeat("x", 4096)
	tail := first
	tail.Record.MessageID = "tail"
	tail.Metadata.Ordinal = 3
	in.Messages = append(in.Messages, middle, tail)
	in.Cutoff = 3
	a, _ := archive.EncodeEnvelope(first)
	b, _ := archive.EncodeEnvelope(tail)
	c := DefaultConfig()
	c.MaxInputBytes = len(a) + len(b) + 2
	d, err := Plan(c, *first.Metadata.CapturedAt, in)
	if err != nil || !d.Ready || len(d.Selected) != 1 || d.Manifest.PendingOriginals != 2 {
		t.Fatalf("prefix skipped middle: %+v %v", d, err)
	}
}
func TestEvidenceAndJobContextAreDistinct(t *testing.T) {
	in := exampleInput()
	now := in.Messages[0].Metadata.CapturedAt.Add(15 * time.Minute)
	a, err := Plan(DefaultConfig(), now, in)
	if err != nil {
		t.Fatal(err)
	}
	in.Cutoff = 20
	b, err := Plan(DefaultConfig(), now, in)
	if err != nil || a.JobID != b.JobID || a.EvidenceHash == b.EvidenceHash {
		t.Fatal("observation evidence and job identity conflated")
	}
	for _, kind := range []string{"generator", "config", "source", "branch"} {
		t.Run(kind, func(t *testing.T) {
			in := exampleInput()
			c := DefaultConfig()
			switch kind {
			case "generator":
				in.GeneratorVersion = "extractive/2"
			case "config":
				c.Version = "summary-config/2"
			case "source":
				in.Messages[0].Record.Text = "changed factual source"
			case "branch":
				in.Scope.BranchKnown = true
				in.Scope.Branch = "explicit-branch"
			}
			d, err := Plan(c, now, in)
			if err != nil || d.JobID == a.JobID {
				t.Fatalf("job context not bound: %s %v", kind, err)
			}
		})
	}
}
func TestCoverageMatchesEverySourceProofField(t *testing.T) {
	in := exampleInput()
	now := in.Messages[0].Metadata.CapturedAt.Add(15 * time.Minute)
	for _, kind := range []string{"provider", "parent", "consent", "record hash", "envelope hash", "capture time"} {
		t.Run(kind, func(t *testing.T) {
			in := exampleInput()
			d, err := Plan(DefaultConfig(), now, in)
			if err != nil {
				t.Fatal(err)
			}
			ref := d.Manifest.Sources[0]
			switch kind {
			case "provider":
				ref.Provider = "other"
			case "parent":
				ref.ParentID = "forged"
			case "consent":
				ref.ConsentEpoch++
			case "record hash":
				ref.RecordHash = strings.Repeat("0", 64)
			case "envelope hash":
				ref.EnvelopeHash = strings.Repeat("0", 64)
			case "capture time":
				v := ref.Metadata.CapturedAt.Add(time.Second)
				ref.Metadata.CapturedAt = &v
			}
			in.Covered = []SourceRef{ref}
			if _, err := Plan(DefaultConfig(), now, in); err == nil {
				t.Fatal("forged source proof accepted")
			}
		})
	}
}
