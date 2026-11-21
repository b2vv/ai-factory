package main

import (
	"context"
	"errors"
	"testing"
	"time"
)

func TestIndexSweepLegacyRowsDoNotTriggerCatchup(t *testing.T) {
	calls := 0
	progress, err := indexSweep(context.Background(), 3, func() (int, bool, error) { calls++; return 100, false, nil })
	if err != nil || progress || calls != 3 {
		t.Fatal("legacy scan count became backlog signal", calls, progress, err)
	}
}
func TestIndexSweepFindsMetadataProgressAcrossQuietProjects(t *testing.T) {
	calls := 0
	progress, err := indexSweep(context.Background(), 4, func() (int, bool, error) { calls++; return 1, calls == 3, nil })
	if err != nil || !progress || calls != 4 {
		t.Fatal("quiet project hid committed metadata progress", calls, progress, err)
	}
}
func TestIndexSweepCancellationAndFailureStopFurtherWork(t *testing.T) {
	ctx, cancel := context.WithCancel(context.Background())
	calls := 0
	_, err := indexSweep(ctx, 64, func() (int, bool, error) { calls++; cancel(); return 1, true, nil })
	if !errors.Is(err, context.Canceled) || calls != 1 {
		t.Fatal("continued after cancellation", calls, err)
	}
	failure := errors.New("synthetic index failure")
	calls = 0
	_, err = indexSweep(context.Background(), 64, func() (int, bool, error) { calls++; return 1, true, failure })
	if !errors.Is(err, failure) || calls != 1 {
		t.Fatal("continued after failed commit", calls, err)
	}
	calls = 0
	_, err = indexSweep(context.Background(), 1000, func() (int, bool, error) { calls++; return 0, false, nil })
	if err != nil || calls != 64 {
		t.Fatal("unbounded project sweep", calls, err)
	}
}

func TestIndexCatchupBurstYieldsAndResetsOnQuietOrError(t *testing.T) {
	const backoff = 7 * time.Second
	busy := 0
	for n := 0; n < 8; n++ {
		delay, next := nextIndexDelay(backoff, true, true, true, busy)
		if delay != 25*time.Millisecond || next != n+1 {
			t.Fatal("active metadata catchup policy", n, delay, next)
		}
		busy = next
	}
	if delay, next := nextIndexDelay(backoff, true, true, true, busy); delay != backoff || next != 0 {
		t.Fatal("burst never yielded", delay, next)
	}
	for _, state := range []struct {
		name                   string
		drain, index, progress bool
	}{
		{"idle-or-legacy", true, true, false}, {"drain-failure", false, true, true}, {"index-failure", true, false, true},
	} {
		t.Run(state.name, func(t *testing.T) {
			delay, next := nextIndexDelay(backoff, state.drain, state.index, state.progress, 4)
			if delay != backoff || next != 0 {
				t.Fatal("non-progress bypassed backoff", delay, next)
			}
			if delay, next := nextIndexDelay(backoff, true, true, true, next); delay != 25*time.Millisecond || next != 1 {
				t.Fatal("recovery did not restart bounded burst", delay, next)
			}
		})
	}
}
