package search_test

import (
	"aifactory.local/storage/internal/archive"
	"aifactory.local/storage/internal/search"
	"aifactory.local/storage/internal/summary"
	"testing"
	"time"
)

func TestProjectionTextUsesLiteralExcerptsAndNULTokenBoundary(t *testing.T) {
	at := time.Date(2026, 1, 1, 0, 0, 0, 0, time.UTC)
	original := archive.Envelope{Version: 2, Record: archive.Record{Project: "p", Provider: "synthetic", SourceInstance: "i", SessionID: "s", MessageID: "m", Type: archive.TypeMessage, Role: "user", Text: "First\nSecond\x00tail", ConsentEpoch: 1}, Metadata: archive.Metadata{Generation: "g", Ordinal: 1, CapturedAt: &at}}
	baseline := summary.Baseline{Project: "p", Generation: "g", Ordinal: 0, At: at.Add(-time.Minute)}
	second := original
	second.Record.MessageID = "m2"
	second.Record.Text = "Another excerpt"
	second.Metadata.Ordinal = 2
	in := summary.Input{Scope: summary.Scope{Project: "p", Provider: "synthetic", SourceInstance: "i", SessionID: "s"}, Generation: "g", Cutoff: 2, Complete: true, Activation: &baseline, Messages: []archive.Envelope{original, second}}
	now := at.Add(15 * time.Minute)
	doc, d, err := summary.GenerateExtract(summary.DefaultConfig(), now, in, summary.DefaultExtractOptions())
	if err != nil || !d.Ready {
		t.Fatal(err)
	}
	record, err := summary.SealExtract(doc, summary.Authority{ConsentEpoch: 1, Activation: baseline}, in.Messages, now)
	if err != nil {
		t.Fatal(err)
	}
	e := archive.Envelope{Version: 2, Record: record, Metadata: archive.Metadata{Generation: "g", Ordinal: 3, CapturedAt: &now, DerivedKind: archive.DerivedSessionExtract}}
	text, err := search.ProjectionText(e)
	if err != nil || text != "First\nSecond tail\nAnother excerpt" {
		t.Fatal("proof wrapper or encoded escapes indexed", text, err)
	}
	if e.Record.Text != record.Text || search.RecordHash(e.Record) != search.RecordHash(record) {
		t.Fatal("projection changed source payload")
	}
	e.Metadata.DerivedKind = ""
	e.Record.Text = "manual\x00note"
	if text, err = search.ProjectionText(e); err != nil || text != "manual note" {
		t.Fatal("manual summary classified by ID prefix", text, err)
	}
	e.Metadata.DerivedKind = archive.DerivedSessionExtract
	e.Record.Text = "{}"
	if _, err = search.ProjectionText(e); err == nil {
		t.Fatal("malformed marked body indexed")
	}
}
