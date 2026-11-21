package search

import (
	"aifactory.local/storage/internal/archive"
	"context"
	"errors"
	"github.com/jackc/pgx/v5/pgxpool"
	"github.com/jackc/puddle/v2"
	"testing"
	"time"
)

func TestMetadataWritesReturnClosedPoolFailure(t *testing.T) {
	// A closed lazy pool exercises real Begin failure without a database or network.
	pool, err := pgxpool.New(context.Background(), "postgres://fixture:fixture@127.0.0.1:1/fixture?sslmode=disable")
	if err != nil {
		t.Fatal(err)
	}
	pool.Close()
	s := &Store{pool: pool, schemaVersion: 2, timeout: time.Second}
	c := Checkpoint{Project: "p", SourceGeneration: "g", ProjectionGeneration: "i", PolicyRevision: "0"}
	now := time.Date(2026, 11, 5, 0, 0, 0, 0, time.UTC)
	e := archive.Envelope{Version: 2, Record: archive.Record{Project: "p", SessionID: "s", MessageID: "m", Text: "source"}, Metadata: archive.Metadata{Generation: "g", Ordinal: 1, CapturedAt: &now}}
	for _, tc := range []struct {
		name string
		run  func() error
	}{
		{"rebuild", func() error { return s.BeginRebuild(c, "") }},
		{"project", func() error { return s.PutEnvelope(e, c) }},
		{"complete", func() error { return s.CompleteCheckpoint(c, 0) }},
		{"advance", func() error { return s.AdvanceCheckpoint(c, 1) }},
		{"time-window", func() error { _, err := s.TimeWindow(c, "captured_at", nil, nil, 0, ""); return err }},
	} {
		t.Run(tc.name, func(t *testing.T) {
			defer func() {
				if r := recover(); r != nil {
					t.Errorf("Begin failure panicked instead of returning closed-pool error: %v", r)
				}
			}()
			if err := tc.run(); !errors.Is(err, puddle.ErrClosedPool) {
				t.Errorf("lost Begin error: %v", err)
			}
		})
	}
}
