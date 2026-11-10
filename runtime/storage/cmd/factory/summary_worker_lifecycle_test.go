package main

import (
	"aifactory.local/storage/internal/api"
	"aifactory.local/storage/internal/archive"
	"aifactory.local/storage/internal/budget"
	"aifactory.local/storage/internal/config"
	"aifactory.local/storage/internal/control"
	"aifactory.local/storage/internal/ingest"
	"aifactory.local/storage/internal/registry"
	"aifactory.local/storage/internal/summary"
	"context"
	"path/filepath"
	"sync"
	"testing"
	"time"
)

type summaryBlockingDiscovery struct {
	*archive.MemStore
	entered, release chan struct{}
	once             sync.Once
}

func (s *summaryBlockingDiscovery) NextSummarySession(archive.SummaryQuery, *archive.SessionKey) (archive.SessionKey, bool, error) {
	s.once.Do(func() { close(s.entered) })
	<-s.release
	return archive.SessionKey{}, false, nil
}
func TestSessionExtractLifecycleCancelsAndJoinsInFlightDiscovery(t *testing.T) {
	root := t.TempDir()
	d, err := control.Initialize(filepath.Join(root, "control"))
	if err != nil {
		t.Fatal(err)
	}
	defer d.Close()
	op := registry.Principal{Kind: registry.Operator}
	if err = d.MintProject(op, "p", "synthetic"); err != nil {
		t.Fatal(err)
	}
	if _, err = d.SetConsent(op, "p", "synthetic", "capture", true); err != nil {
		t.Fatal(err)
	}
	if err = d.BeginArchiveMigration(op, "p", "g"); err != nil {
		t.Fatal(err)
	}
	source := &summaryBlockingDiscovery{MemStore: archive.NewMemStore(), entered: make(chan struct{}), release: make(chan struct{})}
	i, err := ingest.Open(filepath.Join(root, "ingest"), config.NewAccountant(config.Default()), source)
	if err != nil {
		t.Fatal(err)
	}
	defer i.Close()
	ledger, err := budget.Initialize(filepath.Join(root, "budget"), budget.Policy{LiveCap: 1 << 30}, func() (budget.Sample, error) { return budget.LocalSample(root, 1<<30) })
	if err != nil {
		t.Fatal(err)
	}
	if err = d.AttachBudget(ledger); err != nil {
		t.Fatal(err)
	}
	if err = i.SetBudget(ledger); err != nil {
		t.Fatal(err)
	}
	if err = d.WithArchiveTransaction(op, "p", func(tx *control.ArchiveTransaction) error {
		return tx.FinishMigration(func(control.ArchiveState) error { return nil })
	}); err != nil {
		t.Fatal(err)
	}
	if _, err = d.SetConsent(op, "p", "synthetic", "summary", true); err != nil {
		t.Fatal(err)
	}
	srv := api.New(d, config.Default(), "op", "synthetic-only")
	srv.SetIngestor(i)
	srv.SetUsageMeter(func() (config.Usage, error) { return config.Usage{FreeBytes: 1 << 40}, nil })
	if err = srv.ConfigureSummaries(summary.DefaultConfig(), summary.DefaultExtractOptions()); err != nil {
		t.Fatal(err)
	}
	parent, cancel := context.WithCancel(context.Background())
	defer cancel()
	stop := startSessionExtractWorker(parent, srv, time.Hour)
	var release sync.Once
	unblock := func() { release.Do(func() { close(source.release) }) }
	defer unblock()
	select {
	case <-source.entered:
	case <-time.After(2 * time.Second):
		t.Fatal("configured worker did not enter synthetic discovery")
	}
	stopped := make(chan struct{})
	started := make(chan struct{})
	go func() { close(started); stop(); close(stopped) }()
	<-started
	select {
	case <-stopped:
		t.Fatal("stop returned before in-flight source call completed")
	case <-time.After(30 * time.Millisecond):
	}
	unblock()
	select {
	case <-stopped:
	case <-time.After(2 * time.Second):
		cancel()
		t.Fatal("stop did not cancel poll and join worker after source release")
	}
	if _, _, err = d.ArchiveState("p"); err != nil {
		t.Fatal("worker lifecycle damaged still-open authority", err)
	}
}
