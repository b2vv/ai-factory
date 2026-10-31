package ingest

import (
	"aifactory.local/storage/internal/archive"
	"aifactory.local/storage/internal/config"
	"fmt"
	"sync"
	"testing"
)

func TestExplicitReclaimMixedLegacyPendingQuarantineRestart(t *testing.T) {
	dir := t.TempDir()
	store := archive.NewMemStore()
	acct := config.NewAccountant(config.Default())
	i, e := Open(dir, acct, store)
	if e != nil {
		t.Fatal(e)
	}
	usage := config.Usage{FreeBytes: 1 << 40}
	published := archive.Record{Project: "p", MessageID: "published", Text: "source"}
	legacy := archive.Record{Project: "p", MessageID: "legacy", Text: "legacy"}
	quarantined := archive.Record{Project: "q", MessageID: "quarantine", Text: "retained"}
	pending := archive.Record{Project: "p", MessageID: "pending", Text: "pending"}
	for key, r := range map[string]archive.Record{archive.IdentityKey(published): published, "opaque-alias": legacy, archive.IdentityKey(quarantined): quarantined} {
		if _, e = i.Accept(key, r, usage); e != nil {
			t.Fatal(e)
		}
	}
	gate := func(r archive.Record) bool { return r.Project == "p" }
	if _, e = i.DrainGated(gate); e != nil {
		t.Fatal(e)
	}
	if _, e = i.Accept(archive.IdentityKey(pending), pending, usage); e != nil {
		t.Fatal(e)
	}
	total := i.AcceptedBytes()
	result, e := i.Reclaim()
	if e != nil || result.Dropped != 1 {
		t.Fatal(result, e)
	}
	if i.AcceptedBytes() != total {
		t.Fatal("reclaim reset process reservation total")
	}
	progress, e := i.Progress()
	if e != nil || progress.Accepted != 3 || progress.Depth != 1 {
		t.Fatal(progress, e)
	}
	i.Close()
	i, e = Open(dir, acct, store)
	if e != nil {
		t.Fatal(e)
	}
	defer i.Close()
	for key, want := range map[string]string{archive.IdentityKey(published): "archive_committed", "opaque-alias": "archive_committed", archive.IdentityKey(pending): "durable_accepted", archive.IdentityKey(quarantined): "quarantined"} {
		project := "p"
		if key == archive.IdentityKey(quarantined) {
			project = "q"
		}
		state, e := i.RecordState(key, project)
		if e != nil || state.State != want {
			t.Fatal(key, state, e)
		}
	}
	if _, e = i.DrainGated(gate); e != nil {
		t.Fatal(e)
	}
	if _, e = i.Reclaim(); e != nil {
		t.Fatal(e)
	}
	if _, e = store.Purge("p", ""); e != nil {
		t.Fatal(e)
	}
	if _, e = i.Compact(func(r archive.Record) bool { return r.Project != "p" }); e != nil {
		t.Fatal(e)
	}
	if _, e = i.DrainGated(func(archive.Record) bool { return false }); e != nil {
		t.Fatal(e)
	}
	if len(store.All("p")) != 0 {
		t.Fatal("purged project resurrected")
	}
	state, e := i.RecordState(archive.IdentityKey(quarantined), "q")
	if e != nil || state.State != "quarantined" {
		t.Fatal("other quarantine erased", state, e)
	}
}
func TestExplicitReclaimConcurrentAcceptDrainKeepsCanonicalReceipts(t *testing.T) {
	i, e := Open(t.TempDir(), config.NewAccountant(config.Default()), archive.NewMemStore())
	if e != nil {
		t.Fatal(e)
	}
	defer i.Close()
	usage := config.Usage{FreeBytes: 1 << 40}
	var wg sync.WaitGroup
	errors := make(chan error, 100)
	for n := 0; n < 30; n++ {
		r := archive.Record{Project: "p", MessageID: fmt.Sprint(n)}
		if _, e = i.Accept(archive.IdentityKey(r), r, usage); e != nil {
			t.Fatal(e)
		}
	}
	if _, e = i.Drain(); e != nil {
		t.Fatal(e)
	}
	wg.Add(2)
	go func() {
		defer wg.Done()
		for n := 0; n < 10; n++ {
			if _, e := i.Reclaim(); e != nil {
				errors <- e
			}
		}
	}()
	go func() {
		defer wg.Done()
		for n := 30; n < 60; n++ {
			r := archive.Record{Project: "p", MessageID: fmt.Sprint(n)}
			if _, e := i.Accept(archive.IdentityKey(r), r, usage); e != nil {
				errors <- e
			}
			if _, e := i.Drain(); e != nil {
				errors <- e
			}
		}
	}()
	wg.Wait()
	close(errors)
	for e := range errors {
		t.Fatal(e)
	}
	for n := 0; n < 60; n++ {
		key := archive.IdentityKey(archive.Record{Project: "p", MessageID: fmt.Sprint(n)})
		state, e := i.RecordState(key, "p")
		if e != nil || state.State != "archive_committed" {
			t.Fatal(key, state, e)
		}
	}
}
