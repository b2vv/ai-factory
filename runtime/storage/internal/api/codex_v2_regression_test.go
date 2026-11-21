package api_test

import (
	"aifactory.local/storage/internal/api"
	"aifactory.local/storage/internal/archive"
	"aifactory.local/storage/internal/config"
	"aifactory.local/storage/internal/control"
	"aifactory.local/storage/internal/ingest"
	"aifactory.local/storage/internal/registry"
	"aifactory.local/storage/internal/wal"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"path/filepath"
	"testing"
)

func v2Fixture(text string) map[string]any {
	return map[string]any{"project": "p", "provider": "synthetic", "source_instance": "i", "messages": []map[string]any{{"session_id": "s", "message_id": "m", "text": text}}}
}
func TestCodexV2APIConflict409(t *testing.T) {
	ts, _, _, ctl := captureServer(t, archive.NewMemStore(), nil)
	o := registry.Principal{Kind: registry.Operator}
	ctl.MintProject(o, "p", "p")
	ctl.SetConsent(o, "p", "synthetic", "capture", true)
	do(t, http.MethodPost, ts.URL+"/v1/capture", opHdr(), v2Fixture("original"))
	code, _ := do(t, http.MethodPost, ts.URL+"/v1/capture", opHdr(), v2Fixture("changed"))
	if code != 409 {
		t.Fatalf("conflict HTTP=%d", code)
	}
}
func TestCodexV2LegacyKeyConflict(t *testing.T) {
	ts, _, ing, ctl := captureServer(t, archive.NewMemStore(), nil)
	o := registry.Principal{Kind: registry.Operator}
	ctl.MintProject(o, "p", "p")
	ctl.SetConsent(o, "p", "synthetic", "capture", true)
	r := archive.Record{Project: "p", Provider: "synthetic", SourceInstance: "i", SessionID: "s", MessageID: "m", Type: archive.TypeMessage, Text: "original", ConsentEpoch: 1}
	ing.Accept("p|i|s|m", r, config.Usage{FreeBytes: 1 << 40})
	ing.Drain()
	code, body := do(t, http.MethodPost, ts.URL+"/v1/capture", opHdr(), v2Fixture("changed"))
	if code != 409 {
		t.Fatalf("legacy identity conflict admitted HTTP=%d response=%v", code, body)
	}
}
func TestCodexV2BatchLiveHeadroom(t *testing.T) {
	for _, which := range []string{"live", "headroom"} {
		t.Run(which, func(t *testing.T) {
			d := t.TempDir()
			ctl, e := control.Initialize(filepath.Join(d, "ctl"))
			if e != nil {
				t.Fatal(e)
			}
			defer ctl.Close()
			o := registry.Principal{Kind: registry.Operator}
			ctl.MintProject(o, "p", "p")
			ctl.SetConsent(o, "p", "synthetic", "capture", true)
			r := archive.Record{Project: "p", Provider: "synthetic", SourceInstance: "i", SessionID: "s", MessageID: "a", Type: archive.TypeMessage, Text: "x", ConsentEpoch: 1}
			b, _ := json.Marshal(r)
			cost := wal.RecordCost(archive.IdentityKey(r), b)
			cfg := config.Default()
			cfg.CaptureEnabled = true
			u := config.Usage{FreeBytes: 1 << 40}
			if which == "live" {
				cfg.LiveCapBytes = cost
			} else {
				u.FreeBytes = cfg.FreeHeadroom + cost
			}
			s := archive.NewMemStore()
			ing, e := ingest.Open(filepath.Join(d, "ing"), config.NewAccountant(cfg), s)
			if e != nil {
				t.Fatal(e)
			}
			defer ing.Close()
			srv := api.New(ctl, cfg, "op", opSecret)
			srv.SetIngestor(ing)
			srv.SetUsageMeter(func() (config.Usage, error) { return u, nil })
			ts := httptest.NewServer(srv.Handler())
			defer ts.Close()
			fx := v2Fixture("x")
			fx["messages"] = []map[string]any{{"session_id": "s", "message_id": "a", "text": "x"}, {"session_id": "s", "message_id": "b", "text": "x"}}
			code, body := do(t, http.MethodPost, ts.URL+"/v1/capture", opHdr(), fx)
			n, _ := ing.AcceptedCount()
			if n > 1 {
				t.Fatalf("%s budget for one record admitted %d HTTP=%d body=%v", which, n, code, body)
			}
		})
	}
}
