package api

import (
	"aifactory.local/storage/internal/control"
	"aifactory.local/storage/internal/search"
	"testing"
)

func TestIndexFreshnessNeverClaimsCaptureCompleteness(t *testing.T) {
	state := control.ArchiveState{Generation: "g", MigrationComplete: true, CommittedOrdinal: 7, PolicyRevision: 3}
	c := search.Checkpoint{SourceGeneration: "g", PolicyRevision: "3", Ordinal: 7, Complete: true}
	if indexFreshness(&state, &c, true) != "caught_up" {
		t.Fatal("matching checkpoint")
	}
	if indexFreshness(nil, &c, true) != "not_activated" {
		t.Fatal("legacy assumed current")
	}
	if indexFreshness(&state, &c, false) != "unavailable" {
		t.Fatal("backend ignored")
	}
	if indexFreshness(&state, nil, true) != "building" {
		t.Fatal("missing checkpoint")
	}
	for _, mutate := range []func(*search.Checkpoint){func(c *search.Checkpoint) { c.SourceGeneration = "other" }, func(c *search.Checkpoint) { c.PolicyRevision = "2" }, func(c *search.Checkpoint) { c.Ordinal = 6 }, func(c *search.Checkpoint) { c.Complete = false }} {
		stale := c
		mutate(&stale)
		if indexFreshness(&state, &stale, true) != "behind" {
			t.Fatal("stale checkpoint", stale)
		}
	}
	state.MigrationComplete = false
	if indexFreshness(&state, &c, true) != "migration_incomplete" {
		t.Fatal("incomplete migration")
	}
}
