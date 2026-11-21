package api_test

import (
	"aifactory.local/storage/internal/archive"
	"aifactory.local/storage/internal/registry"
	"fmt"
	"net/http"
	"net/url"
	"strings"
	"testing"
)

func TestBoundedWindowCanAdvancePastEntireWithheldWindow(t *testing.T) {
	s := archive.NewMemStore()
	ts, _, _, ctl := captureServer(t, s, nil)
	op := registry.Principal{ID: "op", Kind: registry.Operator}
	ctl.MintProject(op, "p", "p")
	ctl.SetConsent(op, "p", "synthetic", "capture", true)
	_, g := do(t, http.MethodPost, ts.URL+"/v1/grants", opHdr(), map[string]any{"principal_id": "a1", "kind": "agent", "projects": []string{"p"}, "ops": []string{"archive.query"}, "secret": "sek"})
	ep := itoa(int64(g["epoch"].(float64)))
	for n := 0; n < archive.ScanRecords+1; n++ {
		session := "hidden"
		if n == archive.ScanRecords {
			session = "visible"
		}
		s.Put(archive.Record{Project: "p", Provider: "synthetic", SessionID: session, MessageID: fmt.Sprint(n), Seq: n, ConsentEpoch: 1})
	}
	ctl.Retention().DeleteSession("p", "hidden", 1)
	code, b := agentQuery(t, ts.URL, "/v1/archive/query?project=p&limit=1", "a1", ep, "sek")
	if code != 200 || len(b["hits"].([]any)) != 0 {
		t.Fatal(code, b)
	}
	if _, ok := b["total"]; ok {
		t.Fatal("partial window disclosed false total")
	}
	cursor, ok := b["next_cursor"].(string)
	if !ok || strings.Contains(cursor, "hidden") {
		t.Fatal("missing/private cursor", b)
	}
	code, b = agentQuery(t, ts.URL, "/v1/archive/query?project=p&limit=1&cursor="+url.QueryEscape(cursor), "a1", ep, "sek")
	if code != 200 || len(b["hits"].([]any)) != 1 || b["hits"].([]any)[0].(map[string]any)["SessionID"] != "visible" {
		t.Fatal(code, b)
	}
	code, _ = agentQuery(t, ts.URL, "/v1/archive/query?project=p&q=changed&cursor="+url.QueryEscape(cursor), "a1", ep, "sek")
	if code != 400 {
		t.Fatal("cursor accepted under another filter", code)
	}
}
func TestHealthHidesGlobalIngestionWithoutOperator(t *testing.T) {
	ts, _, _, _ := captureServer(t, archive.NewMemStore(), nil)
	_, b := do(t, http.MethodGet, ts.URL+"/health", nil, nil)
	if _, ok := b["ingestion"]; ok {
		t.Fatal("global counters unauthenticated")
	}
	_, b = do(t, http.MethodGet, ts.URL+"/health", opHdr(), nil)
	ing, ok := b["ingestion"].(map[string]any)
	if !ok {
		t.Fatal("operator diagnostics missing")
	}
	if _, ok = ing["committed"]; ok {
		t.Fatal("checkpoint called archive commitment")
	}
	if _, ok = ing["processed"]; !ok {
		t.Fatal("truthful processed field missing")
	}
}
