package archive_test

import (
	"aifactory.local/storage/internal/archive"
	"encoding/json"
	"testing"
	"time"
)

func TestEnvelopePreservesLegacyRecordAndSourceTime(t *testing.T) {
	r := archive.Record{Project: "p", SourceInstance: "i", SessionID: "s", MessageID: "m", Text: "source", ConsentEpoch: 1}
	old, e := json.Marshal(r)
	if e != nil {
		t.Fatal(e)
	}
	legacy, e := archive.DecodeEnvelope(1, old)
	if e != nil || legacy.Record != r || legacy.Metadata.CapturedAt != nil || legacy.Metadata.SourceEventTime != nil {
		t.Fatal(legacy, e)
	}
	capture := time.Date(2026, 11, 5, 12, 0, 0, 0, time.UTC)
	event := capture.Add(-time.Hour)
	env := archive.Envelope{Version: 2, Record: r, Metadata: archive.Metadata{Generation: "generation", Ordinal: 1, CapturedAt: &capture, SourceEventTime: &event}}
	raw, e := archive.EncodeEnvelope(env)
	if e != nil {
		t.Fatal(e)
	}
	got, e := archive.DecodeEnvelope(2, raw)
	if e != nil || got.Record != r || !got.Metadata.CapturedAt.Equal(capture) || !got.Metadata.SourceEventTime.Equal(event) {
		t.Fatal(got, e)
	}
	restored, _ := json.Marshal(got.Record)
	if string(restored) != string(old) {
		t.Fatal("historical record/hash input changed")
	}
}

func TestEnvelopeRejectsInvalidMetadata(t *testing.T) {
	now := time.Date(2026, 11, 5, 12, 0, 0, 0, time.UTC)
	base := archive.Envelope{Version: 2, Record: archive.Record{Project: "p", SessionID: "s", MessageID: "m"}, Metadata: archive.Metadata{Generation: "g", Ordinal: 1, CapturedAt: &now}}
	for name, change := range map[string]func(*archive.Envelope){
		"version":         func(e *archive.Envelope) { e.Version = 3 },
		"generation":      func(e *archive.Envelope) { e.Metadata.Generation = "" },
		"ordinal":         func(e *archive.Envelope) { e.Metadata.Ordinal = 0 },
		"negative":        func(e *archive.Envelope) { e.Metadata.Ordinal = -1 },
		"capture_unknown": func(e *archive.Envelope) { e.Metadata.CapturedAt = nil },
		"legacy_capture":  func(e *archive.Envelope) { e.Metadata.Legacy = true },
		"legacy_event": func(e *archive.Envelope) {
			e.Metadata.Legacy = true
			e.Metadata.CapturedAt = nil
			e.Metadata.SourceEventTime = &now
		},
		"zero_capture": func(e *archive.Envelope) { z := time.Time{}; e.Metadata.CapturedAt = &z },
		"zero_event":   func(e *archive.Envelope) { z := time.Time{}; e.Metadata.SourceEventTime = &z },
	} {
		t.Run(name, func(t *testing.T) {
			e := base
			change(&e)
			if _, err := archive.EncodeEnvelope(e); err == nil {
				t.Fatal("invalid encode accepted")
			}
			raw, _ := json.Marshal(e)
			if _, err := archive.DecodeEnvelope(2, raw); err == nil {
				t.Fatal("invalid decode accepted")
			}
		})
	}
	for _, raw := range []string{`null`, `{}`, `{"version":2}`, `{"version":2,"version":3}`, `[]`, `{} {}`} {
		if _, err := archive.DecodeEnvelope(2, []byte(raw)); err == nil {
			t.Fatalf("invalid wire accepted: %s", raw)
		}
	}
	if _, err := archive.DecodeEnvelope(3, []byte(`{}`)); err == nil {
		t.Fatal("unknown format accepted")
	}
	base.Metadata.Legacy = true
	base.Metadata.CapturedAt = nil
	raw, err := archive.EncodeEnvelope(base)
	if err != nil {
		t.Fatal(err)
	}
	got, err := archive.DecodeEnvelope(2, raw)
	if err != nil || !got.Metadata.Legacy || got.Metadata.CapturedAt != nil {
		t.Fatal(got, err)
	}
}

func TestEnvelopeCanonicalizesTimesWithoutChangingRecord(t *testing.T) {
	local := time.Date(2026, 11, 5, 14, 0, 0, 0, time.FixedZone("offset", 7200))
	e := archive.Envelope{Version: 2, Record: archive.Record{Project: "p", SessionID: "s", MessageID: "m", Text: "\u03aa\u03b6\u03b1\u03ba"}, Metadata: archive.Metadata{Generation: "g", Ordinal: 1, CapturedAt: &local, SourceEventTime: &local}}
	raw, err := archive.EncodeEnvelope(e)
	if err != nil {
		t.Fatal(err)
	}
	got, err := archive.DecodeEnvelope(2, raw)
	if err != nil {
		t.Fatal(err)
	}
	if got.Record != e.Record || got.Metadata.CapturedAt.Location() != time.UTC || got.Metadata.SourceEventTime.Location() != time.UTC || !got.Metadata.CapturedAt.Equal(local) {
		t.Fatal(got)
	}
	if e.Metadata.CapturedAt.Location() == time.UTC {
		t.Fatal("caller mutated")
	}
}
