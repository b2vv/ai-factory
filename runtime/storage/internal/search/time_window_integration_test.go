//go:build integration

package search

import (
	"aifactory.local/storage/internal/archive"
	"fmt"
	"reflect"
	"testing"
	"time"
)

func TestTimeWindowBoundsCandidatesAndExcludesLateCommit(t *testing.T) {
	s := metadataStore(t)
	c := Checkpoint{Project: "p", SourceGeneration: "s", ProjectionGeneration: "g", PolicyRevision: "0"}
	if err := s.BeginRebuild(c, ""); err != nil {
		t.Fatal(err)
	}
	event := time.Date(2026, 11, 5, 12, 0, 0, 123456789, time.UTC)
	for n := 1; n <= 103; n++ {
		captured := event.Add(time.Duration(n) * time.Second)
		e := archive.Envelope{Version: 2, Record: archive.Record{Project: "p", SessionID: "s", MessageID: fmt.Sprint(n), Text: "needle Stra\u00dfe"}, Metadata: archive.Metadata{Generation: "s", Ordinal: int64(n), CapturedAt: &captured, SourceEventTime: &event}}
		if n == 1 {
			e.Metadata.SourceEventTime = nil
		}
		if err := s.PutEnvelope(e, c); err != nil {
			t.Fatal(err)
		}
		c.Ordinal = int64(n)
	}
	if err := s.CompleteCheckpoint(c, 103); err != nil {
		t.Fatal(err)
	}
	c.Complete = true
	first, err := s.TimeWindow(c, "source_event_time", &event, nil, 103, "missing")
	if err != nil || len(first.References) != 0 || first.Next == nil {
		t.Fatal("empty raw page lost continuation", first, err)
	}
	first, err = s.TimeWindow(c, "source_event_time", &event, nil, 103, "STRASSE")
	if err != nil || len(first.References) != 100 || first.Next == nil {
		t.Fatal(len(first.References), first.Next, err)
	}
	for n, ref := range first.References {
		if n == 0 {
			if ref.Before != nil {
				t.Fatal("first reference invented previous position")
			}
			continue
		}
		previous := first.References[n-1]
		want := TimePosition{Time: previous.Time, Key: hash(previous.Identity)}
		if ref.Before == nil || *ref.Before != want {
			t.Fatal("reference lost exact preceding candidate", n, ref.Before, want)
		}
	}
	late := archive.Envelope{Version: 2, Record: archive.Record{Project: "p", SessionID: "s", MessageID: "late", Text: "needle Stra\u00dfe"}, Metadata: archive.Metadata{Generation: "s", Ordinal: 104, CapturedAt: &event, SourceEventTime: &event}}
	if err := s.PutEnvelope(late, c); err != nil {
		t.Fatal(err)
	}
	second, err := s.TimeWindow(c, "source_event_time", &event, first.Next, 103, "STRASSE")
	if err != nil || len(second.References) != 2 || second.Next != nil {
		t.Fatal(second, err)
	}
	if !reflect.DeepEqual(second.References[0].Before, first.Next) {
		t.Fatal("continued page lost incoming position")
	}
	seen := map[string]bool{}
	for _, r := range append(first.References, second.References...) {
		if seen[r.Identity] || r.Ordinal > 103 {
			t.Fatal("duplicate/late result", r)
		}
		seen[r.Identity] = true
	}
	captured, err := s.TimeWindow(c, "captured_at", nil, nil, 103, "")
	if err != nil || len(captured.References) != 100 || captured.Next == nil || captured.References[0].Ordinal != 103 {
		t.Fatal("captured order", captured, err)
	}
	later := event.Add(time.Nanosecond)
	none, err := s.TimeWindow(c, "source_event_time", &later, nil, 103, "")
	if err != nil || len(none.References) != 0 || none.Next != nil {
		t.Fatal("since nanosecond precision", none, err)
	}
	next := c
	next.ProjectionGeneration = "replacement"
	next.Ordinal = 0
	next.Complete = false
	if err := s.BeginRebuild(next, c.ProjectionGeneration); err != nil {
		t.Fatal(err)
	}
	if _, err := s.TimeWindow(c, "source_event_time", nil, first.Next, 103, ""); err == nil {
		t.Fatal("old generation cursor accepted")
	}
}
