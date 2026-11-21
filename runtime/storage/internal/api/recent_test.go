package api

import (
	"aifactory.local/storage/internal/search"
	"strings"
	"testing"
)

func TestRecentCursorMaximumAcceptedBindings(t *testing.T) {
	s := &Server{opSec: "synthetic-only"}
	for _, value := range []string{strings.Repeat("x", 4096), strings.Repeat("\x00", 4096)} {
		c := pageCursor{Project: value, Query: value, Provider: value, Time: &timeCursor{Field: "captured_at", Checkpoint: search.Checkpoint{Project: value, SourceGeneration: "g", ProjectionGeneration: "r", PolicyRevision: "1", Ordinal: 105, Complete: true}, Upper: 105, After: &search.TimePosition{Time: "2026-01-01T00:00:00.000000000Z", Key: strings.Repeat("a", 64)}}}
		token, err := s.encodeCursor(c)
		if err != nil {
			t.Fatal(err)
		}
		if len(token) > 8192 {
			t.Fatalf("accepted fields create unusable cursor: %d", len(token))
		}
		got, err := s.decodeCursor(token)
		if err != nil || got.Time == nil || got.Time.Upper != 105 {
			t.Fatal(got, err)
		}
	}
}
