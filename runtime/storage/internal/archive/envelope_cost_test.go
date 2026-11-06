package archive_test

import (
	"aifactory.local/storage/internal/archive"
	"testing"
	"time"
)

func TestEnvelopeReservationRetainsRecordAndMetadataLiability(t *testing.T) {
	now := time.Date(2026, 1, 2, 3, 4, 5, 123, time.UTC)
	record := archive.Record{Project: "p", SourceInstance: "source", SessionID: "s", MessageID: "m", Text: "original"}
	for _, legacy := range []bool{true, false} {
		e := archive.Envelope{Version: 2, Record: record, Metadata: archive.Metadata{Generation: "g", Ordinal: 1, Legacy: legacy}}
		if !legacy {
			e.Metadata.CapturedAt = &now
		}
		cost, err := archive.EnvelopeReservationBytes(e)
		if err != nil || cost <= archive.ReservationBytes(record) {
			t.Fatalf("metadata/index liability omitted: %d %v", cost, err)
		}
		larger := e
		larger.Record.Text += "Unicode Ж🙂"
		grown, err := archive.EnvelopeReservationBytes(larger)
		if err != nil || grown-cost != int64(len("Unicode Ж🙂")) {
			t.Fatalf("UTF-8 payload charge: %d %v", grown-cost, err)
		}
		retry, err := archive.EnvelopeReservationBytes(e)
		if err != nil || retry != cost {
			t.Fatal("reservation is not repeatable", retry, err)
		}
		malformed := e
		malformed.Metadata.Ordinal = 0
		if charge, err := archive.EnvelopeReservationBytes(malformed); err == nil || charge != 0 {
			t.Fatal("invalid envelope has a usable charge", charge, err)
		}
	}
}
