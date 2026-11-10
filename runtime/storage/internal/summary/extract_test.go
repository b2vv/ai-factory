package summary

import (
	"aifactory.local/storage/internal/archive"
	"encoding/json"
	"fmt"
	"reflect"
	"runtime"
	"runtime/debug"
	"strings"
	"testing"
	"time"
)

func TestExtractIsLiteralAndExplicit(t *testing.T) {
	in := exampleInput()
	in.GeneratorVersion = ""
	now := in.Messages[0].Metadata.CapturedAt.Add(15 * time.Minute)
	opts := DefaultExtractOptions()
	opts.MaxExcerptBytes = 5
	doc, d, err := GenerateExtract(DefaultConfig(), now, in, opts)
	if err != nil {
		t.Fatal(err)
	}
	if !d.Ready || doc.Kind != "extractive" || doc.Format != "ai-factory.session-extract/1" || doc.JobID != d.JobID || !doc.GeneratedAt.Equal(now) {
		t.Fatalf("invalid extract identity: %+v", doc)
	}
	if len(doc.Excerpts) != 1 {
		t.Fatal("source omitted")
	}
	e := doc.Excerpts[0]
	if e.Text != "A con" || e.Start != 0 || e.End != 5 || !e.Truncated || e.SourceBytes != len(in.Messages[0].Record.Text) || e.Identity.MessageID != "m1" || e.Role != "user" {
		t.Fatalf("fabricated excerpt or scope: %+v", e)
	}
	if doc.Manifest.CaptureCompleteness != "unknown" || doc.Notice == "" {
		t.Fatal("missing limits/proof")
	}
}

func TestExtractBudgetsFullPayloadWithoutPartialCoverage(t *testing.T) {
	in := exampleInput()
	in.GeneratorVersion = ""
	now := in.Messages[0].Metadata.CapturedAt.Add(15 * time.Minute)
	o := DefaultExtractOptions()
	o.MaxExcerptBytes = 1
	o.MaxDocumentBytes = 1
	doc, _, err := GenerateExtract(DefaultConfig(), now, in, o)
	if err == nil || doc.Kind != "" {
		t.Fatal("oversized proof returned as partial extract")
	}
}
func TestExtractUnicodeEmptyAndNotDue(t *testing.T) {
	in := exampleInput()
	in.GeneratorVersion = ""
	in.Messages[0].Record.Text = "🙂éx"
	now := in.Messages[0].Metadata.CapturedAt.Add(15 * time.Minute)
	o := DefaultExtractOptions()
	o.MaxExcerptBytes = 5
	doc, _, err := GenerateExtract(DefaultConfig(), now, in, o)
	if err != nil || doc.Excerpts[0].Text != "🙂" || doc.Excerpts[0].End != 4 || !doc.Excerpts[0].Truncated {
		t.Fatalf("invalid UTF-8 prefix: %+v %v", doc, err)
	}
	in.Messages[0].Record.Text = ""
	doc, _, err = GenerateExtract(DefaultConfig(), now, in, o)
	if err != nil || len(doc.Excerpts) != 1 || doc.Excerpts[0].Text != "" || doc.Excerpts[0].Truncated {
		t.Fatal("empty original misrepresented")
	}
	doc, d, err := GenerateExtract(DefaultConfig(), now.Add(-14*time.Minute), in, o)
	if err != nil || d.Ready || doc.Kind != "" {
		t.Fatal("not-due produced content")
	}
}
func TestExtractorOwnsSemanticProcessingIdentity(t *testing.T) {
	in := exampleInput()
	in.GeneratorVersion = ""
	now := in.Messages[0].Metadata.CapturedAt.Add(15 * time.Minute)
	a := DefaultExtractOptions()
	a.MaxExcerptBytes = 5
	doc, _, err := GenerateExtract(DefaultConfig(), now, in, a)
	if err != nil {
		t.Fatal(err)
	}
	b := a
	b.MaxExcerptBytes = 6
	other, _, err := GenerateExtract(DefaultConfig(), now, in, b)
	if err != nil || other.JobID == doc.JobID {
		t.Fatal("different extraction reused job identity")
	}
	b = a
	b.MaxDocumentBytes = 10000
	other, _, err = GenerateExtract(DefaultConfig(), now, in, b)
	if err != nil || other.JobID != doc.JobID || other.Excerpts[0].Text != doc.Excerpts[0].Text {
		t.Fatal("admission-only bound changed semantic identity")
	}
	in.GeneratorVersion = "fake-generator"
	if _, _, err := GenerateExtract(DefaultConfig(), now, in, a); err == nil {
		t.Fatal("forged generator label accepted")
	}
}

func TestExtractExactEncodedBoundaryAndAllSources(t *testing.T) {
	in := exampleInput()
	in.GeneratorVersion = ""
	in.Messages[0].Record.Text = "\"\n<🙂"
	second := in.Messages[0]
	second.Record.MessageID = "m2"
	second.Metadata.Ordinal++
	in.Messages = append(in.Messages, second)
	in.Cutoff++
	now := in.Messages[0].Metadata.CapturedAt.Add(15 * time.Minute)
	o := DefaultExtractOptions()
	doc, _, err := GenerateExtract(DefaultConfig(), now, in, o)
	if err != nil {
		t.Fatal(err)
	}
	raw, err := json.Marshal(doc)
	if err != nil {
		t.Fatal(err)
	}
	o.MaxDocumentBytes = len(raw)
	fit, _, err := GenerateExtract(DefaultConfig(), now, in, o)
	if err != nil || len(fit.Excerpts) != 2 || fit.Excerpts[0].Text != "\"\n<🙂" {
		t.Fatalf("exact encoded boundary rejected: %v", err)
	}
	o.MaxDocumentBytes--
	refused, _, err := GenerateExtract(DefaultConfig(), now, in, o)
	if err == nil || refused.Format != "" || len(refused.Excerpts) != 0 {
		t.Fatal("partial coverage escaped output budget")
	}
}

func TestExtractOptionAndInputValidation(t *testing.T) {
	in := exampleInput()
	in.GeneratorVersion = ""
	now := in.Messages[0].Metadata.CapturedAt.Add(15 * time.Minute)
	for _, o := range []ExtractOptions{{0, 100}, {-1, 100}, {1, 0}, {1, -1}, {1, 1<<20 + 1}, {101, 100}} {
		if _, e := ExtractiveVersion(o); e == nil {
			t.Fatalf("invalid options admitted: %+v", o)
		}
		if d, _, e := GenerateExtract(DefaultConfig(), now, in, o); e == nil || d.Format != "" {
			t.Fatal("invalid options generated document")
		}
	}
	for _, name := range []string{"scope", "utf8", "time"} {
		bad := exampleInput()
		bad.GeneratorVersion = ""
		at := now
		switch name {
		case "scope":
			bad.Scope.Project = "foreign"
		case "utf8":
			bad.Messages[0].Record.Text = string([]byte{255})
		case "time":
			at = time.Time{}
		}
		if doc, _, e := GenerateExtract(DefaultConfig(), at, bad, DefaultExtractOptions()); e == nil || doc.Format != "" {
			t.Fatalf("Plan error swallowed: %s", name)
		}
	}
	o := DefaultExtractOptions()
	version, e := ExtractiveVersion(o)
	if e != nil {
		t.Fatal(e)
	}
	in.GeneratorVersion = version
	if _, _, e = GenerateExtract(DefaultConfig(), now, in, o); e != nil {
		t.Fatalf("real extractor label refused: %v", e)
	}
}
func TestExtractCoverageAndPositionsAreExact(t *testing.T) {
	in := exampleInput()
	in.GeneratorVersion = ""
	first := in.Messages[0]
	first.Record.Text = "short"
	second := first
	second.Metadata.Ordinal++
	second.Record.MessageID = "m2"
	second.Record.Role = "assistant"
	second.Record.Text = "answer"
	in.Messages = []archive.Envelope{second, first}
	in.Cutoff++
	now := first.Metadata.CapturedAt.Add(15 * time.Minute)
	o := DefaultExtractOptions()
	o.MaxExcerptBytes = 5
	doc, d, e := GenerateExtract(DefaultConfig(), now, in, o)
	if e != nil {
		t.Fatal(e)
	}
	version, versionErr := ExtractiveVersion(o)
	if versionErr != nil || doc.Manifest.GeneratorVersion != version {
		t.Fatal("extractor identity not bound into coverage")
	}
	if !reflect.DeepEqual(doc.Manifest, d.Manifest) || doc.EvidenceHash != d.EvidenceHash || doc.Extractor != ExtractorID || doc.ExcerptBytes != 5 || !strings.Contains(doc.Notice, "not a semantic summary") {
		t.Fatal("provenance altered")
	}
	want := []Excerpt{
		{Identity: Identity{"p", "src", "s", "m1"}, Role: "user", Text: "short", End: 5, SourceBytes: 5},
		{Identity: Identity{"p", "src", "s", "m2"}, Role: "assistant", Text: "answe", End: 5, SourceBytes: 6, Truncated: true},
	}
	// The fixture's source IDs are authoritative; inspect all fields rather than accepting counts.
	want[0].Identity = Identity{first.Record.Project, first.Record.SourceInstance, first.Record.SessionID, "m1"}
	want[1].Identity = Identity{second.Record.Project, second.Record.SourceInstance, second.Record.SessionID, "m2"}
	if !reflect.DeepEqual(doc.Excerpts, want) {
		t.Fatalf("source order, identity or byte ranges changed: %+v", doc.Excerpts)
	}
}
func TestExtractHeaderRefusedBeforeLargeSerialization(t *testing.T) {
	in := exampleInput()
	in.GeneratorVersion = ""
	c := DefaultConfig()
	c.MaxInputBytes = 1 << 20
	c.MaxReferenceBytes = 1 << 20
	first := in.Messages[0]
	first.Record.SourceInstance = strings.Repeat("x", 4096)
	first.Record.SessionID = strings.Repeat("s", 4096)
	in.Scope.SourceInstance = first.Record.SourceInstance
	in.Scope.SessionID = first.Record.SessionID
	in.Messages = nil
	for i := 0; i < 24; i++ {
		e := first
		e.Record.MessageID = fmt.Sprintf("m%d", i)
		e.Metadata.Ordinal = int64(i + 1)
		in.Messages = append(in.Messages, e)
	}
	in.Cutoff = 24
	now := first.Metadata.CapturedAt.Add(15 * time.Minute)
	o := ExtractOptions{1, 10000}
	version, e := ExtractiveVersion(o)
	if e != nil {
		t.Fatal(e)
	}
	in.GeneratorVersion = version
	baseline := allocatedExtractBytes(func() {
		if _, e := Plan(c, now, in); e != nil {
			t.Fatal(e)
		}
	})
	limited := allocatedExtractBytes(func() {
		d, _, e := GenerateExtract(c, now, in, o)
		if e == nil || d.Format != "" {
			t.Fatal("oversized proof admitted")
		}
	})
	if delta := limited - baseline; delta > 128<<10 {
		t.Fatalf("output admission allocated %d extra bytes/op before refusal", delta)
	}
}

func TestExtractRefusesEachIncompleteDocumentBudget(t *testing.T) {
	in := exampleInput()
	in.GeneratorVersion = ""
	in.Messages[0].Record.Text = strings.Repeat("x", 2048)
	now := in.Messages[0].Metadata.CapturedAt.Add(15 * time.Minute)
	for _, excerptBytes := range []int{1, 256} {
		o := DefaultExtractOptions()
		o.MaxExcerptBytes = excerptBytes
		full, _, err := GenerateExtract(DefaultConfig(), now, in, o)
		if err != nil {
			t.Fatal(err)
		}
		raw, _ := json.Marshal(full)
		full.Excerpts = []Excerpt{}
		header, _ := json.Marshal(full)
		caps := []int{len(header) - 1, len(header), len(raw) - 1}
		if excerptBytes == 256 {
			caps = append(caps, len(header)+128)
		}
		for _, cap := range caps {
			o.MaxDocumentBytes = cap
			doc, _, err := GenerateExtract(DefaultConfig(), now, in, o)
			if err == nil || doc.Format != "" || len(doc.Excerpts) != 0 {
				t.Fatalf("partial extract at cap %d: %v", cap, err)
			}
		}
	}
}
func TestExtractPrefixAdmissionPrecedesLargeSerialization(t *testing.T) {
	in := exampleInput()
	in.GeneratorVersion = ""
	in.Messages[0].Record.Text = strings.Repeat("x", 1<<20)
	now := in.Messages[0].Metadata.CapturedAt.Add(15 * time.Minute)
	c := DefaultConfig()
	c.MaxInputBytes = 4 << 20
	o := ExtractOptions{1 << 20, 1 << 20}
	in.GeneratorVersion, _ = ExtractiveVersion(o)
	baseline := allocatedExtractBytes(func() {
		if _, e := Plan(c, now, in); e != nil {
			t.Fatal(e)
		}
	})
	limited := allocatedExtractBytes(func() {
		doc, _, e := GenerateExtract(c, now, in, o)
		if e == nil || doc.Format != "" {
			t.Fatal("oversized complete extract admitted")
		}
	})
	if delta := limited - baseline; delta > 128<<10 {
		t.Fatalf("prefix admission allocated %d extra bytes/op", delta)
	}
}

func TestExtractFixedHeaderAdmissionPrecedesSerialization(t *testing.T) {
	in := exampleInput()
	in.GeneratorVersion = ""
	in.Scope.BranchKnown = true
	in.Scope.Branch = strings.Repeat("b", 4096)
	now := in.Messages[0].Metadata.CapturedAt.Add(15 * time.Minute)
	c := DefaultConfig()
	o := ExtractOptions{1, 512}
	in.GeneratorVersion, _ = ExtractiveVersion(o)
	baseline := allocatedExtractBytes(func() {
		if _, e := Plan(c, now, in); e != nil {
			t.Fatal(e)
		}
	})
	limited := allocatedExtractBytes(func() {
		doc, _, e := GenerateExtract(c, now, in, o)
		if e == nil || doc.Format != "" {
			t.Fatal("oversized header admitted")
		}
	})
	if delta := limited - baseline; delta > 4<<10 {
		t.Fatalf("fixed header admission allocated %d extra bytes/op", delta)
	}
}

// Compare the same public planning path with/without output admission. Fixed warm
// calls and a bounded loop prevent GC clearing json pools in only one measurement.
// Tests are not parallel; GC/processor settings are restored before returning.
func allocatedExtractBytes(call func()) int64 {
	runtime.GC()
	gc := debug.SetGCPercent(-1)
	procs := runtime.GOMAXPROCS(1)
	defer func() { debug.SetGCPercent(gc); runtime.GOMAXPROCS(procs); runtime.GC() }()
	call()
	call()
	var before, after runtime.MemStats
	runtime.ReadMemStats(&before)
	for i := 0; i < 5; i++ {
		call()
	}
	runtime.ReadMemStats(&after)
	return int64(after.TotalAlloc-before.TotalAlloc) / 5
}
