package api_test

import (
	"aifactory.local/storage/internal/api"
	"aifactory.local/storage/internal/archive"
	"aifactory.local/storage/internal/config"
	"aifactory.local/storage/internal/control"
	"aifactory.local/storage/internal/ingest"
	"aifactory.local/storage/internal/registry"
	"net/http"
	"net/http/httptest"
	"path/filepath"
	"sync"
	"sync/atomic"
	"testing"
)

func TestCodexV3CrossRequestBudget(t *testing.T) {
	for _, dimension := range []string{"live", "headroom"} {
		t.Run(dimension, func(t *testing.T) {
			d := t.TempDir()
			ctl, e := control.Initialize(filepath.Join(d, "ctl"))
			if e != nil {
				t.Fatal(e)
			}
			defer ctl.Close()
			op := registry.Principal{Kind: registry.Operator}
			ctl.MintProject(op, "p", "p")
			ctl.SetConsent(op, "p", "synthetic", "capture", true)
			r := archive.Record{Project: "p", Provider: "synthetic", SourceInstance: "i", SessionID: "s", MessageID: "a", Type: archive.TypeMessage, Text: "x", ConsentEpoch: 1}
			cost := ingest.RecordCost(r)
			cfg := config.Default()
			cfg.CaptureEnabled = true
			u := config.Usage{FreeBytes: 1 << 40}
			if dimension == "live" {
				cfg.LiveCapBytes = cost
			} else {
				u.FreeBytes = cfg.FreeHeadroom + cost
			}
			store := archive.NewMemStore()
			ing, e := ingest.Open(filepath.Join(d, "ing"), config.NewAccountant(cfg), store)
			if e != nil {
				t.Fatal(e)
			}
			defer ing.Close()
			srv := api.New(ctl, cfg, "op", opSecret)
			srv.SetIngestor(ing)
			var measured atomic.Int32
			both := make(chan struct{})
			srv.SetUsageMeter(func() (config.Usage, error) {
				if measured.Add(1) == 2 {
					close(both)
				}
				<-both
				return u, nil
			})
			ts := httptest.NewServer(srv.Handler())
			defer ts.Close()
			var wg sync.WaitGroup
			for _, id := range []string{"a", "b"} {
				wg.Add(1)
				go func(id string) {
					defer wg.Done()
					fx := v2Fixture("x")
					fx["messages"] = []map[string]any{{"session_id": "s", "message_id": id, "text": "x"}}
					do(t, http.MethodPost, ts.URL+"/v1/capture", opHdr(), fx)
				}(id)
			}
			wg.Wait()
			n, e := ing.AcceptedCount()
			if e != nil {
				t.Fatal(e)
			}
			if n > 1 {
				t.Fatalf("two requests reused one-record %s budget: accepted=%d measurements=%d", dimension, n, measured.Load())
			}
		})
	}
}
