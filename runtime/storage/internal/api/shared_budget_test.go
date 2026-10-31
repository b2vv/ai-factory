package api_test

import (
	"aifactory.local/storage/internal/archive"
	"aifactory.local/storage/internal/config"
	"aifactory.local/storage/internal/registry"
	"net/http"
	"testing"
)

func TestSharedBudgetControlRefusesFullLiveBudget(t *testing.T) {
	ts, srv, _, ctl := captureServer(t, archive.NewMemStore(), nil)
	srv.SetSharedUsageMeter(func() (config.Usage, error) {
		return config.Usage{LiveBytes: config.Default().LiveCapBytes, FreeBytes: 1 << 40}, nil
	})
	code, body := do(t, http.MethodPost, ts.URL+"/v1/projects", opHdr(), map[string]any{"uuid": "budget-denied", "label": "synthetic"})
	if code != 503 {
		t.Fatalf("full shared budget HTTP=%d body=%v", code, body)
	}
	if ctl.ReservedBytes() != 0 {
		t.Fatal("refused mutation reserved a WAL write")
	}
	// Refusal may follow an in-memory authority-reducing mutation: fail closed.
	if e := ctl.MintProject(registry.Principal{Kind: registry.Operator}, "later", "later"); e == nil {
		t.Fatal("capacity failure left control serving authority")
	}
}

func TestPurgeStagingRefusalIsPartialAndKeepsWAL(t *testing.T) {
	store := archive.NewMemStore()
	ts, srv, ing, ctl := captureServer(t, store, nil)
	op := registry.Principal{Kind: registry.Operator}
	if e := ctl.MintProject(op, "p", "p"); e != nil {
		t.Fatal(e)
	}
	if _, e := ctl.SetConsent(op, "p", "synthetic", "capture", true); e != nil {
		t.Fatal(e)
	}
	if code, _ := do(t, http.MethodPost, ts.URL+"/v1/capture", opHdr(), v2Fixture("erase")); code != 200 {
		t.Fatal(code)
	}
	if _, e := ctl.DeleteProjectBarrier(op, "p"); e != nil {
		t.Fatal(e)
	}
	srv.SetUsageMeter(func() (config.Usage, error) {
		return config.Usage{LiveBytes: config.Default().LiveCapBytes, FreeBytes: 1 << 40}, nil
	})
	code, body := do(t, http.MethodPost, ts.URL+"/v1/purge/project", opHdr(), map[string]any{"project": "p"})
	if code != 503 || body["complete"] != false {
		t.Fatalf("unfunded staging reported erasure success: %d %v", code, body)
	}
	if len(store.All("p")) != 0 {
		t.Fatal("archive-first deletion did not run")
	}
	if n, e := ing.AcceptedCount(); e != nil || n != 1 {
		t.Fatal("refused staging changed durable WAL", n, e)
	}
}
