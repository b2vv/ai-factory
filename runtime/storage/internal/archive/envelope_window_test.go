package archive_test

import (
	"aifactory.local/storage/internal/archive"
	"errors"
	"fmt"
	"strings"
	"testing"
)

func testEnvelopeScan(t *testing.T, s interface {
	archive.MetadataStore
	ScanEnvelopes(string, string, int64, int64) (archive.EnvelopeWindow, error)
}) {
	t.Helper()
	for n := 102; n >= 1; n-- {
		e := archive.Envelope{Version: 2, Record: archive.Record{Project: "p", SessionID: "s", MessageID: fmt.Sprint(n)}, Metadata: archive.Metadata{Generation: "g", Ordinal: int64(n), Legacy: true}}
		if err := s.PutEnvelope(e); err != nil {
			t.Fatal(err)
		}
	}
	w, err := s.ScanEnvelopes("p", "g", 0, 101)
	if err != nil || len(w.Records) != 100 || !w.More || w.Records[0].Metadata.Ordinal != 1 || w.Records[99].Metadata.Ordinal != 100 {
		t.Fatal(len(w.Records), w.More, err)
	}
	w, err = s.ScanEnvelopes("p", "g", 100, 101)
	if err != nil || len(w.Records) != 1 || w.More || w.Records[0].Metadata.Ordinal != 101 {
		t.Fatal(w, err)
	}
	w, err = s.ScanEnvelopes("p", "g", 101, 101)
	if err != nil || len(w.Records) != 0 || w.More {
		t.Fatal(w, err)
	}
	w, err = s.ScanEnvelopes("other", "g", 0, 101)
	if err != nil || len(w.Records) != 0 {
		t.Fatal(w, err)
	}
	w, err = s.ScanEnvelopes("p", "wrong", 0, 101)
	if err != nil || len(w.Records) != 0 {
		t.Fatal(w, err)
	}
	collision := archive.Envelope{Version: 2, Record: archive.Record{Project: "p", SessionID: "s", MessageID: "collision"}, Metadata: archive.Metadata{Generation: "g", Ordinal: 1, Legacy: true}}
	if err := s.PutEnvelope(collision); !errors.Is(err, archive.ErrIDConflict) {
		t.Fatal("duplicate ordinal accepted", err)
	}
	if _, err := s.ScanEnvelopes("p", "g", -1, 101); err == nil {
		t.Fatal("negative position accepted")
	}
}

func TestEnvelopeScanUsesCommittedOrdinalRange(t *testing.T) {
	testEnvelopeScan(t, archive.NewMemStore())
}

func TestEnvelopeScanByteBoundAndContinuation(t *testing.T) {
	s := archive.NewMemStore()
	for n := 1; n <= 2; n++ {
		e := archive.Envelope{Version: 2, Record: archive.Record{Project: "p", SessionID: "s", MessageID: fmt.Sprint(n), Text: strings.Repeat("x", archive.ScanBytes/2)}, Metadata: archive.Metadata{Generation: "g", Ordinal: int64(n), Legacy: true}}
		if err := s.PutEnvelope(e); err != nil {
			t.Fatal(err)
		}
	}
	first, err := s.ScanEnvelopes("p", "g", 0, 2)
	if err != nil || len(first.Records) != 1 || !first.More {
		t.Fatal(len(first.Records), first.More, err)
	}
	next, err := s.ScanEnvelopes("p", "g", first.Records[0].Metadata.Ordinal, 2)
	if err != nil || len(next.Records) != 1 || next.More || next.Records[0].Metadata.Ordinal != 2 {
		t.Fatal(len(next.Records), next.More, err)
	}
	large := archive.Envelope{Version: 2, Record: archive.Record{Project: "large", SessionID: "s", MessageID: "m", Text: strings.Repeat("x", archive.ScanBytes)}, Metadata: archive.Metadata{Generation: "g", Ordinal: 1, Legacy: true}}
	if err := s.PutEnvelope(large); err != nil {
		t.Fatal(err)
	}
	if _, err := s.ScanEnvelopes("large", "g", 0, 1); !errors.Is(err, archive.ErrRecordTooLarge) {
		t.Fatal("oversized first record", err)
	}
}
