package main

import (
	"aifactory.local/storage/internal/api"
	"aifactory.local/storage/internal/archive"
	"aifactory.local/storage/internal/config"
	"aifactory.local/storage/internal/control"
	"aifactory.local/storage/internal/ingest"
	"aifactory.local/storage/internal/registry"
	"context"
	"path/filepath"
	"testing"
	"time"
)

type v2SignalStore struct {
	*archive.MemStore
	put chan struct{}
}

func (s *v2SignalStore) Put(r archive.Record) error {
	e := s.MemStore.Put(r)
	select {
	case s.put <- struct{}{}:
	default:
	}
	return e
}
func TestCodexV2ActualWorkerReplaysReopenedWAL(t *testing.T) {
	d := t.TempDir()
	ctl, e := control.Initialize(filepath.Join(d, "ctl"))
	if e != nil {
		t.Fatal(e)
	}
	defer ctl.Close()
	op := registry.Principal{Kind: registry.Operator}
	ctl.MintProject(op, "p", "p")
	ctl.SetConsent(op, "p", "synthetic", "capture", true)
	s := &v2SignalStore{archive.NewMemStore(), make(chan struct{}, 1)}
	c := config.Default()
	i, e := ingest.Open(filepath.Join(d, "wal"), config.NewAccountant(c), s)
	if e != nil {
		t.Fatal(e)
	}
	_, e = i.Accept("k", archive.Record{Project: "p", Provider: "synthetic", MessageID: "m", ConsentEpoch: 1}, config.Usage{FreeBytes: 1 << 40})
	if e != nil {
		t.Fatal(e)
	}
	i.Close()
	i, e = ingest.Open(filepath.Join(d, "wal"), config.NewAccountant(c), s)
	if e != nil {
		t.Fatal(e)
	}
	defer i.Close()
	srv := api.New(ctl, c, "op", "secret")
	srv.SetIngestor(i)
	ctx, cancel := context.WithCancel(context.Background())
	done := make(chan struct{})
	go func() { defer close(done); drainWorker(ctx, srv) }()
	select {
	case <-s.put:
	case <-time.After(5 * time.Second):
		cancel()
		<-done
		t.Fatal("worker did not replay reopened pending WAL")
	}
	cancel()
	select {
	case <-done:
	case <-time.After(5 * time.Second):
		t.Fatal("worker failed to stop")
	}
}
