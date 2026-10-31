package api_test

// F5 (/health drain depth/lag/gaps) and F10 (/v1/ingest/{receipt} state) observability.

import (
	"fmt"
	"net/http"
	"net/url"
	"testing"

	"aifactory.local/storage/internal/archive"
	"aifactory.local/storage/internal/config"
	"aifactory.local/storage/internal/registry"
)

func TestF5HealthDrainBacklog(t *testing.T) {
	store := archive.NewMemStore()
	ts, srv, ing, ctl := captureServer(t, store, nil)
	op := registry.Principal{ID: "op", Kind: registry.Operator}
	ctl.MintProject(op, "p", "p")
	ctl.SetConsent(op, "p", "synthetic", "capture", true)

	// Accept 3 records while the archive is DOWN so they stay durable-accepted (undrained).
	store.SetAvailable(false)
	for i := 0; i < 3; i++ {
		r := archive.Record{Project: "p", Provider: "synthetic", SourceInstance: "i", SessionID: "s", MessageID: fmt.Sprintf("m%d", i), Seq: 0, Type: archive.TypeMessage, Role: "user", Text: "x", ConsentEpoch: 1}
		if _, e := ing.Accept(archive.IdentityKey(r), r, config.Usage{FreeBytes: 1 << 40}); e != nil {
			t.Fatal(e)
		}
	}

	ingblk := func() map[string]any {
		_, b := do(t, http.MethodGet, ts.URL+"/health", opHdr(), nil)
		m, ok := b["ingestion"].(map[string]any)
		if !ok {
			t.Fatalf("/health missing ingestion block: %v", b)
		}
		return m
	}

	m := ingblk()
	if m["depth"].(float64) != 3 {
		t.Fatalf("depth must be 3 before drain, got %v", m["depth"])
	}
	if m["blocked"].(bool) {
		t.Fatalf("must not be blocked on a clean journal")
	}
	if m["lag_seq"].(float64) == 0 {
		t.Fatalf("lag_seq must be >0 with an undrained backlog, got %v", m["lag_seq"])
	}
	if m["accepted"].(float64) != 3 {
		t.Fatalf("accepted must be 3, got %v", m["accepted"])
	}

	// Recover the archive and drain; depth returns to 0, lag clears.
	store.SetAvailable(true)
	if n, e := srv.DrainOnce(); e != nil || n != 3 {
		t.Fatalf("drain n=%d err=%v", n, e)
	}
	m = ingblk()
	if m["depth"].(float64) != 0 {
		t.Fatalf("depth must be 0 after drain, got %v", m["depth"])
	}
	if m["lag_seq"].(float64) != 0 {
		t.Fatalf("lag_seq must be 0 after drain, got %v", m["lag_seq"])
	}
}

func TestF10IngestReceiptState(t *testing.T) {
	store := archive.NewMemStore()
	ts, srv, ing, ctl := captureServer(t, store, nil)
	op := registry.Principal{ID: "op", Kind: registry.Operator}
	ctl.MintProject(op, "p", "p")
	ctl.SetConsent(op, "p", "synthetic", "capture", true)
	_, gm := do(t, http.MethodPost, ts.URL+"/v1/grants", opHdr(), map[string]any{"principal_id": "a1", "kind": "agent", "projects": []string{"p"}, "ops": []string{"archive.query"}, "secret": "sek"})
	epoch := itoa(int64(gm["epoch"].(float64)))

	r := archive.Record{Project: "p", Provider: "synthetic", SourceInstance: "i", SessionID: "s", MessageID: "m1", Type: archive.TypeMessage, Role: "user", Text: "x", ConsentEpoch: 1}
	key := archive.IdentityKey(r)
	path := func(k string) string { return "/v1/ingest/" + url.PathEscape(k) + "?project=p" }

	// Accept while the archive is down -> durable_accepted (pending drain).
	store.SetAvailable(false)
	if _, e := ing.Accept(key, r, config.Usage{FreeBytes: 1 << 40}); e != nil {
		t.Fatal(e)
	}
	code, b := agentQuery(t, ts.URL, path(key), "a1", epoch, "sek")
	if code != 200 || b["state"] != "durable_accepted" {
		t.Fatalf("pending receipt must be durable_accepted: code=%d body=%v", code, b)
	}

	// Drain -> archive_committed.
	store.SetAvailable(true)
	if n, e := srv.DrainOnce(); e != nil || n != 1 {
		t.Fatalf("drain n=%d err=%v", n, e)
	}
	_, b = agentQuery(t, ts.URL, path(key), "a1", epoch, "sek")
	if b["state"] != "archive_committed" {
		t.Fatalf("drained receipt must be archive_committed, got %v", b["state"])
	}

	// Unknown receipt -> not_found (200, observability, not an error).
	code, b = agentQuery(t, ts.URL, path("no-such-key"), "a1", epoch, "sek")
	if code != 200 || b["state"] != "not_found" {
		t.Fatalf("unknown receipt must be not_found: code=%d body=%v", code, b)
	}

	// Missing project -> 400; unauthorized -> 403.
	if code, _ := agentQuery(t, ts.URL, "/v1/ingest/"+url.PathEscape(key), "a1", epoch, "sek"); code != http.StatusBadRequest {
		t.Fatalf("missing project must be 400, got %d", code)
	}
	if code, _ := do(t, http.MethodGet, ts.URL+path(key), nil, nil); code != http.StatusForbidden {
		t.Fatalf("unauthorized receipt lookup must be 403, got %d", code)
	}
}
