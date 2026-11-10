package archive_test

import (
	"aifactory.local/storage/internal/archive"
	"testing"
	"time"
)

func TestDerivedMetadataKeepsHistoricalBytesAndRecordIdentity(t *testing.T) {
	old := `{"version":2,"record":{"Project":"p","Provider":"synthetic","SourceInstance":"i","SessionID":"s","MessageID":"m","Seq":0,"ParentID":"","Type":"message","Role":"user","Text":"original","Edited":false,"Withdrawn":false,"ConsentEpoch":1},"metadata":{"generation":"g","ordinal":1,"captured_at":"2026-01-01T00:00:00Z","source_event_time":null,"legacy":false}}`
	e, err := archive.DecodeEnvelope(2, []byte(old))
	if err != nil {
		t.Fatal(err)
	}
	raw, err := archive.EncodeEnvelope(e)
	if err != nil || string(raw) != old {
		t.Fatal("historical canonical bytes changed", string(raw), err)
	}
	before := archive.IdentityKey(e.Record)
	e.Record.Type = archive.TypeSummary
	e.Record.Role = "assistant"
	e.Metadata.DerivedKind = archive.DerivedSessionExtract
	raw, err = archive.EncodeEnvelope(e)
	if err != nil {
		t.Fatal(err)
	}
	got, err := archive.DecodeEnvelope(2, raw)
	if err != nil || got.Metadata.DerivedKind != "session-extract/1" || archive.IdentityKey(got.Record) != before {
		t.Fatal("marker or identity changed", got, err)
	}
	store := archive.NewMemStore()
	if err = store.PutEnvelope(e); err != nil {
		t.Fatal(err)
	}
	persisted, found, err := store.LookupEnvelope(e.Record)
	if err != nil || !found || persisted.Metadata.DerivedKind != archive.DerivedSessionExtract {
		t.Fatal("metadata marker lost", persisted, err)
	}
}
func TestDerivedMetadataRejectsUnknownAndFalseOriginals(t *testing.T) {
	at := time.Date(2026, 1, 1, 0, 0, 0, 0, time.UTC)
	base := archive.Envelope{Version: 2, Record: archive.Record{Project: "p", Type: archive.TypeSummary, Role: "assistant"}, Metadata: archive.Metadata{Generation: "g", Ordinal: 1, CapturedAt: &at, DerivedKind: archive.DerivedSessionExtract}}
	for _, name := range []string{"unknown", "original", "legacy", "invented-event-time"} {
		e := base
		switch name {
		case "unknown":
			e.Metadata.DerivedKind = "future"
		case "original":
			e.Record.Type = archive.TypeMessage
		case "legacy":
			e.Metadata.Legacy = true
			e.Metadata.CapturedAt = nil
		case "invented-event-time":
			e.Metadata.SourceEventTime = &at
		}
		if _, err := archive.EncodeEnvelope(e); err == nil {
			t.Fatalf("invalid derived marker accepted: %s", name)
		}
	}
}
