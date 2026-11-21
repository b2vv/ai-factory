package archive_test

import (
	"aifactory.local/storage/internal/archive"
	"errors"
	"testing"
	"time"
)

func testEnvelopeProjection(t *testing.T, s archive.MetadataStore) {
	t.Helper()
	now := time.Date(2026, 11, 5, 12, 0, 0, 123456789, time.UTC)
	e := archive.Envelope{Version: 2, Record: archive.Record{Project: "metadata-p", SourceInstance: "source", SessionID: "session", MessageID: "message", Text: "original", ConsentEpoch: 1}, Metadata: archive.Metadata{Generation: "g", Ordinal: 1, CapturedAt: &now}}
	bad := e
	invalid := time.Date(10000, 1, 1, 0, 0, 0, 0, time.UTC)
	bad.Metadata.CapturedAt = &invalid
	if err := s.PutEnvelope(bad); err == nil {
		t.Fatal("unreadable capture time accepted")
	}
	bad = e
	bad.Metadata.SourceEventTime = &invalid
	if err := s.PutEnvelope(bad); err == nil {
		t.Fatal("unreadable source time accepted")
	}
	if _, found, err := s.LookupEnvelope(e.Record); err != nil || found {
		t.Fatal("invalid write mutated source", found, err)
	}
	if err := s.PutEnvelope(e); err != nil {
		t.Fatal(err)
	}
	if err := s.PutEnvelope(e); err != nil {
		t.Fatal("replay", err)
	}
	got, found, err := s.LookupEnvelope(e.Record)
	if err != nil || !found || got.Record != e.Record || got.Metadata.Ordinal != 1 || got.Metadata.Generation != "g" || !got.Metadata.CapturedAt.Equal(now) {
		t.Fatal(got, found, err)
	}
	changed := e
	changed.Record.Text = "edited"
	if err := s.PutEnvelope(changed); !errors.Is(err, archive.ErrIDConflict) {
		t.Fatal("content conflict", err)
	}
	changed = e
	changed.Metadata.Ordinal = 2
	if err := s.PutEnvelope(changed); !errors.Is(err, archive.ErrIDConflict) {
		t.Fatal("metadata conflict", err)
	}
	changed = e
	later := now.Add(time.Nanosecond)
	changed.Metadata.CapturedAt = &later
	if err := s.PutEnvelope(changed); !errors.Is(err, archive.ErrIDConflict) {
		t.Fatal("timestamp conflict", err)
	}
	changed = e
	changed.Record.SourceInstance = "other"
	changed.Metadata.Ordinal = 2
	if _, found, err := s.LookupEnvelope(changed.Record); err != nil || found {
		t.Fatal("source alias", found, err)
	}
	if err := s.PutEnvelope(changed); err != nil {
		t.Fatal("source isolation", err)
	}
}
func TestEnvelopeProjection(t *testing.T) { testEnvelopeProjection(t, archive.NewMemStore()) }

func testMetadataMigration(t *testing.T, base archive.Store, s archive.MetadataStore) {
	t.Helper()
	r := archive.Record{Project: "legacy-p", SessionID: "session", MessageID: "message", Text: "unchanged"}
	if err := base.Put(r); err != nil {
		t.Fatal(err)
	}
	old, found, err := s.LookupEnvelope(r)
	if err != nil || !found || old.Version != 1 || !old.Metadata.Legacy || old.Metadata.CapturedAt != nil {
		t.Fatal(old, found, err)
	}
	e := archive.Envelope{Version: 2, Record: r, Metadata: archive.Metadata{Generation: "g", Ordinal: 1, Legacy: true}}
	changed := e
	changed.Record.Text = "changed"
	if err := s.AttachMetadata(changed); !errors.Is(err, archive.ErrIDConflict) {
		t.Fatal("migration overwrote content", err)
	}
	if err := s.AttachMetadata(e); err != nil {
		t.Fatal(err)
	}
	if err := s.AttachMetadata(e); err != nil {
		t.Fatal("migration retry", err)
	}
	got, found, err := s.LookupEnvelope(r)
	if err != nil || !found || got.Record != r || got.Version != 2 || !got.Metadata.Legacy || got.Metadata.CapturedAt != nil || got.Metadata.SourceEventTime != nil {
		t.Fatal(got, found, err)
	}
	changed = e
	changed.Metadata.Generation = "new"
	if err := s.AttachMetadata(changed); !errors.Is(err, archive.ErrIDConflict) {
		t.Fatal("metadata overwritten", err)
	}
	missing := e
	missing.Record.MessageID = "missing"
	if err := s.AttachMetadata(missing); err == nil {
		t.Fatal("migration created missing source")
	}
	if _, found, err := s.LookupEnvelope(missing.Record); err != nil || found {
		t.Fatal(found, err)
	}
	if _, err := base.Purge(r.Project, r.SessionID); err != nil {
		t.Fatal(err)
	}
	if _, found, err := s.LookupEnvelope(r); err != nil || found {
		t.Fatal("purged source visible", found, err)
	}
	// Fake also mirrors physical erasure: a later legacy insert has no retained metadata.
	if err := base.Put(r); err != nil {
		t.Fatal(err)
	}
	got, _, err = s.LookupEnvelope(r)
	if err != nil || got.Version != 1 {
		t.Fatal("metadata survived erasure", got, err)
	}
}
func TestMetadataMigration(t *testing.T) { s := archive.NewMemStore(); testMetadataMigration(t, s, s) }
