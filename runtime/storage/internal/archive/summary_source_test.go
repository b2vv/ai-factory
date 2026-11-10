package archive_test

import (
	"aifactory.local/storage/internal/archive"
	"fmt"
	"strings"
	"testing"
	"time"
)

func testSummarySourceContract(t *testing.T, store archive.SummarySource) {
	t.Helper()
	at := time.Date(2026, 1, 1, 0, 0, 0, 0, time.UTC)
	put := func(ord int64, project, provider, source, session string, epoch int64, kind archive.RecordType, derived bool) {
		e := archive.Envelope{Version: 2, Record: archive.Record{Project: project, Provider: provider, SourceInstance: source, SessionID: session, MessageID: fmt.Sprint(ord), Type: kind, Role: "user", Text: "fixture", ConsentEpoch: epoch}, Metadata: archive.Metadata{Generation: "g", Ordinal: ord, CapturedAt: &at}}
		if derived {
			e.Record.Role = "assistant"
			e.Metadata.DerivedKind = archive.DerivedSessionExtract
		}
		if err := store.PutEnvelope(e); err != nil {
			t.Fatal(err)
		}
	}
	put(1, "p", "v", "a", "s", 1, archive.TypeMessage, false)
	put(2, "p", "v", "a", "old", 1, archive.TypeMessage, false)
	put(3, "p", "v", "a", "s", 1, archive.TypeSummary, true)
	put(4, "p", "v", "a", "s", 3, archive.TypeMessage, false)
	put(5, "p", "v", "b", "s", 3, archive.TypeMessage, false)
	put(6, "p", "v", "a", "s", 3, archive.TypeSummary, false)
	put(7, "foreign", "v", "a", "s", 3, archive.TypeMessage, false)
	put(8, "p", "foreign", "0-provider", "s", 3, archive.TypeMessage, false)
	foreignGeneration := archive.Envelope{Version: 2, Record: archive.Record{Project: "p", Provider: "v", SourceInstance: "0-generation", SessionID: "s", MessageID: "9", Type: archive.TypeMessage, Role: "user", Text: "old generation", ConsentEpoch: 3}, Metadata: archive.Metadata{Generation: "old-g", Ordinal: 9, CapturedAt: &at}}
	if err := store.PutEnvelope(foreignGeneration); err != nil {
		t.Fatal(err)
	}
	withdrawn := foreignGeneration
	withdrawn.Record.SourceInstance = "0-withdrawn"
	withdrawn.Record.MessageID = "10"
	withdrawn.Record.Withdrawn = true
	withdrawn.Metadata.Generation = "g"
	withdrawn.Metadata.Ordinal = 10
	if err := store.PutEnvelope(withdrawn); err != nil {
		t.Fatal(err)
	}
	put(11, "p", "v", "0-future", "s", 4, archive.TypeMessage, false)
	q := archive.SummaryQuery{Project: "p", Provider: "v", Generation: "g", Through: 11, RevokedThrough: 2, CaptureEpoch: 3}
	key, found, err := store.NextSummarySession(q, nil)
	if err != nil || !found || key != (archive.SessionKey{SourceInstance: "a", SessionID: "s"}) {
		t.Fatal("discovery used revoked or foreign records", key, err)
	}
	next, found, err := store.NextSummarySession(q, &key)
	if err != nil || !found || next.SourceInstance != "b" {
		t.Fatal("session cursor did not progress", next, err)
	}
	head, found, err := store.SummaryHead(q, key)
	if err != nil || !found || head.Metadata.Ordinal != 3 {
		t.Fatal("capture revoke hid factual head or selected manual summary", head, err)
	}
	page, err := store.ScanSummaryOriginals(q, key, 0)
	if err != nil || page.More || len(page.Records) != 1 || page.Records[0].Metadata.Ordinal != 4 {
		t.Fatal("input mixed ineligible sources", page, err)
	}
	q.ActivationOrdinal = 3
	if _, found, err = store.SummaryHead(q, key); err != nil || found {
		t.Fatal("old head crossed explicit activation baseline", found, err)
	}
	put(12, "p", "v", "a", "s", 1, archive.TypeSummary, true)
	q.ActivationOrdinal = 0
	q.Through = 12
	latest, found, err := store.SummaryHead(q, key)
	if err != nil || !found || latest.Metadata.Ordinal != 12 {
		t.Fatal("newest factual marked head lost to older head or serving filter", found, err)
	}
}

func TestSummarySourceSeparatesEligibleOriginalsFromHistoricalHead(t *testing.T) {
	testSummarySourceContract(t, archive.NewMemStore())
}

func testSummarySourceIgnoresLegacyInputs(t *testing.T, store archive.SummarySource) {
	t.Helper()
	at := time.Date(2026, 1, 1, 0, 0, 0, 0, time.UTC)
	legacy := archive.Envelope{Version: 2, Record: archive.Record{Project: "legacy-input", Provider: "v", SourceInstance: "a", SessionID: "only-legacy", MessageID: "old", Type: archive.TypeMessage, Role: "user", Text: "unknown historical time", ConsentEpoch: 1}, Metadata: archive.Metadata{Generation: "g", Ordinal: 1, Legacy: true}}
	if err := store.PutEnvelope(legacy); err != nil {
		t.Fatal(err)
	}
	current := legacy
	current.Record.SessionID = "current"
	current.Record.MessageID = "new"
	current.Metadata = archive.Metadata{Generation: "g", Ordinal: 2, CapturedAt: &at}
	if err := store.PutEnvelope(current); err != nil {
		t.Fatal(err)
	}
	q := archive.SummaryQuery{Project: "legacy-input", Provider: "v", Generation: "g", Through: 2, CaptureEpoch: 1}
	first, found, err := store.NextSummarySession(q, nil)
	if err != nil || !found || first.SessionID != "current" {
		t.Fatal("current discovery", first, found, err)
	}
	if next, found, err := store.NextSummarySession(q, &first); err != nil || found {
		t.Fatal("legacy-only session discovered", next, found, err)
	}
	page, err := store.ScanSummaryOriginals(q, archive.SessionKey{SourceInstance: "a", SessionID: "only-legacy"}, 0)
	if err != nil || page.More || len(page.Records) != 0 {
		t.Fatal("legacy original was not excluded", page, err)
	}
}
func TestSummarySourceIgnoresUnverifiableHistoricalInputs(t *testing.T) {
	testSummarySourceIgnoresLegacyInputs(t, archive.NewMemStore())
}

func testSummarySourceUnicodeAndCompletePages(t *testing.T, store archive.SummarySource) {
	t.Helper()
	at := time.Date(2026, 1, 1, 0, 0, 0, 0, time.UTC)
	keys := []string{strings.Repeat("\x00", 4096), "e\u0301", "é", "Ζ", "я", "猫"}
	session := strings.Repeat("α", 2048) // 4096 UTF-8 bytes, shared IDs do not imply shared source.
	ordinal := int64(0)
	put := func(instance string) {
		t.Helper()
		ordinal++
		e := archive.Envelope{Version: 2, Record: archive.Record{Project: "pages", Provider: "v", SourceInstance: instance, SessionID: session, MessageID: fmt.Sprint(ordinal), Type: archive.TypeMessage, Role: "user", Text: "synthetic input", ConsentEpoch: 1}, Metadata: archive.Metadata{Generation: "g", Ordinal: ordinal, CapturedAt: &at}}
		if err := store.PutEnvelope(e); err != nil {
			t.Fatal("fixture insert", ordinal, err)
		}
	}
	for i, key := range keys {
		n := 1
		if i == len(keys)-1 {
			n = 205
		}
		for j := 0; j < n; j++ {
			put(key)
		}
	}
	q := archive.SummaryQuery{Project: "pages", Provider: "v", Generation: "g", Through: ordinal, CaptureEpoch: 1}
	var after *archive.SessionKey
	for i, want := range keys {
		got, found, err := store.NextSummarySession(q, after)
		if err != nil || !found || got.SourceInstance != want || got.SessionID != session {
			t.Fatal("binary Unicode/source keyset", i, found, err)
		}
		detached := got
		after = &detached
	}
	if _, found, err := store.NextSummarySession(q, after); err != nil || found {
		t.Fatal("session enumeration did not exhaust", err)
	}
	last := int64(0)
	seen := 0
	for i, want := range []int{100, 100, 5} {
		page, err := store.ScanSummaryOriginals(q, archive.SessionKey{SourceInstance: "猫", SessionID: session}, last)
		if err != nil || len(page.Records) != want || page.More != (i < 2) {
			t.Fatal("complete original page", i, len(page.Records), page.More, err)
		}
		for _, e := range page.Records {
			seen++
			if e.Metadata.Ordinal != int64(seen+5) {
				t.Fatal("pagination skipped/repeated original", seen, e.Metadata.Ordinal)
			}
			last = e.Metadata.Ordinal
		}
	}
	if seen != 205 || last != 210 {
		t.Fatal("wrong finite coverage", seen, last)
	}
	// A new scope before the old cursor belongs to the next discovery cycle. A
	// fixed Through must not silently include the insert in the current snapshot.
	put("a")
	first := archive.SessionKey{SourceInstance: keys[0], SessionID: session}
	got, found, err := store.NextSummarySession(q, &first)
	if err != nil || !found || got.SourceInstance != "e\u0301" {
		t.Fatal("late insert crossed fixed cutoff", found, err)
	}
	q.Through = ordinal
	got, found, err = store.NextSummarySession(q, &first)
	if err != nil || !found || got.SourceInstance != "a" {
		t.Fatal("new cutoff lost late scope", found, err)
	}
}
func TestSummarySourceUnicodeAndCompletePages(t *testing.T) {
	testSummarySourceUnicodeAndCompletePages(t, archive.NewMemStore())
}
