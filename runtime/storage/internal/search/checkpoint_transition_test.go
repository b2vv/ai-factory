package search_test

import (
	"aifactory.local/storage/internal/archive"
	"aifactory.local/storage/internal/search"
	"testing"
)

func TestCheckpointTransitionContract(t *testing.T) {
	initial := search.Checkpoint{Project: "p", SourceGeneration: "s", ProjectionGeneration: "a", PolicyRevision: "0"}
	tests := []struct {
		name     string
		current  *search.Checkpoint
		desired  search.Checkpoint
		previous string
		want     search.CheckpointAction
	}{
		{"new", nil, initial, "", search.CheckpointReset},
		{"missing_previous", nil, initial, "lost", ""},
		{"same_generation", &search.Checkpoint{Project: "p", SourceGeneration: "s", ProjectionGeneration: "a", PolicyRevision: "0", Ordinal: 5, Complete: true}, initial, "", search.CheckpointReplay},
		{"new_generation", &initial, search.Checkpoint{Project: "p", SourceGeneration: "s", ProjectionGeneration: "b", PolicyRevision: "1"}, "a", search.CheckpointReset},
		{"stale_previous", &initial, search.Checkpoint{Project: "p", SourceGeneration: "s", ProjectionGeneration: "b", PolicyRevision: "1"}, "old", ""},
		{"generation_rebinding", &initial, search.Checkpoint{Project: "p", SourceGeneration: "other", ProjectionGeneration: "a", PolicyRevision: "0"}, "a", ""},
		{"project_collision", &initial, search.Checkpoint{Project: "q", SourceGeneration: "s", ProjectionGeneration: "b", PolicyRevision: "0"}, "a", ""},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got, err := search.RebuildDecision(tt.current, tt.desired, tt.previous)
			if tt.want == "" {
				if err == nil {
					t.Fatal("invalid transition accepted", got)
				}
			} else if err != nil || got != tt.want {
				t.Fatal(got, err)
			}
		})
	}
	e := archive.Envelope{Version: 2, Record: archive.Record{Project: "p", SessionID: "s", MessageID: "m"}, Metadata: archive.Metadata{Generation: "s", Ordinal: 1, Legacy: true}}
	if got, err := search.ProjectionDecision(initial, initial, e); err != nil || got != search.CheckpointAdvance {
		t.Fatal(got, err)
	}
	after := initial
	after.Ordinal = 1
	if got, err := search.ProjectionDecision(after, initial, e); err != nil || got != search.CheckpointVerifyRetry {
		t.Fatal(got, err)
	}
	stale := initial
	stale.ProjectionGeneration = "old"
	if _, err := search.ProjectionDecision(after, stale, e); err == nil {
		t.Fatal("stale projection accepted")
	}
	if _, err := search.ProjectionDecision(after, after, e); err == nil {
		t.Fatal("non-advancing source accepted")
	}
	advanced := after
	advanced.Ordinal = 2
	if _, err := search.ProjectionDecision(advanced, initial, e); err == nil {
		t.Fatal("older replay after later progress accepted")
	}
	if got, err := search.CompletionDecision(after, after, 3); err != nil || got != search.CheckpointComplete {
		t.Fatal(got, err)
	}
	done := after
	done.Ordinal = 3
	done.Complete = true
	if got, err := search.CompletionDecision(done, after, 3); err != nil || got != search.CheckpointReplay {
		t.Fatal(got, err)
	}
	if _, err := search.CompletionDecision(after, after, 0); err == nil {
		t.Fatal("checkpoint regressed")
	}
	if _, err := search.CompletionDecision(done, stale, 3); err == nil {
		t.Fatal("old generation completion accepted")
	}
}

func TestCheckpointRejectsChangedPositionAndAuthority(t *testing.T) {
	expected := search.Checkpoint{Project: "p", SourceGeneration: "s", ProjectionGeneration: "g", PolicyRevision: "0", Ordinal: 1}
	e := archive.Envelope{Version: 2, Record: archive.Record{Project: "p", SessionID: "s", MessageID: "m"}, Metadata: archive.Metadata{Generation: "s", Ordinal: 3, Legacy: true}}
	for _, change := range []struct {
		name   string
		mutate func(*search.Checkpoint)
	}{
		{"source", func(c *search.Checkpoint) { c.SourceGeneration = "changed" }},
		{"policy", func(c *search.Checkpoint) { c.PolicyRevision = "1" }},
		{"complete", func(c *search.Checkpoint) { c.Complete = true }},
		{"ordinal", func(c *search.Checkpoint) { c.Ordinal = 2 }},
	} {
		t.Run(change.name, func(t *testing.T) {
			current := expected
			change.mutate(&current)
			if _, err := search.ProjectionDecision(current, expected, e); err == nil {
				t.Fatal("stale projection accepted")
			}
			if _, err := search.CompletionDecision(current, expected, 4); err == nil {
				t.Fatal("stale completion accepted")
			}
		})
	}
}

func TestIncompleteProgressDecision(t *testing.T) {
	c := search.Checkpoint{Project: "p", SourceGeneration: "s", ProjectionGeneration: "g", PolicyRevision: "0"}
	if a, err := search.ProgressDecision(c, c, 100); err != nil || a != search.CheckpointAdvance {
		t.Fatal(a, err)
	}
	after := c
	after.Ordinal = 100
	if a, err := search.ProgressDecision(after, c, 100); err != nil || a != search.CheckpointReplay {
		t.Fatal(a, err)
	}
	for _, current := range []search.Checkpoint{
		{Project: "p", SourceGeneration: "s", ProjectionGeneration: "g", PolicyRevision: "0", Ordinal: 100, Complete: true},
		{Project: "p", SourceGeneration: "s", ProjectionGeneration: "g", PolicyRevision: "1"},
		{Project: "p", SourceGeneration: "s", ProjectionGeneration: "g", PolicyRevision: "0", Ordinal: 99},
	} {
		if _, err := search.ProgressDecision(current, c, 100); err == nil {
			t.Fatal("stale/incompatible progress", current)
		}
	}
	if _, err := search.ProgressDecision(c, c, 0); err == nil {
		t.Fatal("nonadvancing progress")
	}
}
