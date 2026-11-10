package api_test

// S4: the archive query is BOUNDED by deterministic offset/limit pagination (default + hard
// cap), each hit still carries provenance, and a malformed page parameter is a hard 400 (so a
// caller can never mistake a clamped page for the whole archive).

import (
	"fmt"
	"net/http"
	"net/url"
	"strings"
	"testing"

	"aifactory.local/storage/internal/archive"
	"aifactory.local/storage/internal/registry"
)

// agentQuery issues an authorized GET /v1/archive/query with the agent grant headers.
func agentQuery(t *testing.T, tsURL, path, principal, epoch, secret string) (int, map[string]any) {
	t.Helper()
	return do(t, http.MethodGet, tsURL+path, map[string]string{"X-Principal-Id": principal, "X-Grant-Epoch": epoch, "X-Secret": secret}, nil)
}

func TestS4ArchiveQueryPaginationBounded(t *testing.T) {
	store := archive.NewMemStore()
	ts, _, _, ctl := captureServer(t, store, nil)
	op := registry.Principal{ID: "op", Kind: registry.Operator}
	ctl.MintProject(op, "p", "p")
	ctl.SetConsent(op, "p", "synthetic", "capture", true)
	_, gm := do(t, http.MethodPost, ts.URL+"/v1/grants", opHdr(), map[string]any{"principal_id": "a1", "kind": "agent", "projects": []string{"p"}, "ops": []string{"archive.query"}, "secret": "sek"})
	epoch := itoa(int64(gm["epoch"].(float64)))

	const N = 250
	for i := 0; i < N; i++ {
		// One session, strictly increasing seq => deterministic order (session then seq).
		if err := store.Put(archive.Record{Project: "p", Provider: "synthetic", SourceInstance: "i", SessionID: "s", MessageID: fmt.Sprintf("m%04d", i), Seq: i, Type: archive.TypeMessage, Role: "user", Text: "x", ConsentEpoch: 1}); err != nil {
			t.Fatal(err)
		}
	}

	hitsLen := func(b map[string]any) int { return len(b["hits"].([]any)) }
	num := func(b map[string]any, k string) (float64, bool) { v, ok := b[k].(float64); return v, ok }

	// Default limit: bounded to defaultQueryLimit (100); total reported; next_offset present.
	code, b := agentQuery(t, ts.URL, "/v1/archive/query?project=p", "a1", epoch, "sek")
	if code != http.StatusOK {
		t.Fatalf("default query HTTP=%d body=%v", code, b)
	}
	if got := hitsLen(b); got != 100 {
		t.Fatalf("default page must be bounded to 100, got %d", got)
	}
	if tot, _ := num(b, "total"); tot != N {
		t.Fatalf("total must be %d, got %v", N, b["total"])
	}
	if no, ok := num(b, "next_offset"); !ok || no != 100 {
		t.Fatalf("next_offset must be 100, got %v (ok=%v)", b["next_offset"], ok)
	}
	// Provenance survives on each hit.
	if first := b["hits"].([]any)[0].(map[string]any); first["Provider"] != "synthetic" || first["MessageID"] == "" {
		t.Fatalf("hit missing provenance: %v", first)
	}

	// limit above the hard cap is clamped DOWN to maxQueryLimit (1000) => all 250, last page.
	_, b = agentQuery(t, ts.URL, "/v1/archive/query?project=p&limit=100000", "a1", epoch, "sek")
	if got := hitsLen(b); got != N {
		t.Fatalf("capped limit must return all %d (<cap), got %d", N, got)
	}
	if _, ok := b["next_offset"]; ok {
		t.Fatalf("last page must omit next_offset, got %v", b["next_offset"])
	}

	// A middle page: offset=100 limit=50 => 50 hits, next_offset=150.
	_, b = agentQuery(t, ts.URL, "/v1/archive/query?project=p&offset=100&limit=50", "a1", epoch, "sek")
	if got := hitsLen(b); got != 50 {
		t.Fatalf("middle page must be 50, got %d", got)
	}
	if no, _ := num(b, "next_offset"); no != 150 {
		t.Fatalf("next_offset must be 150, got %v", b["next_offset"])
	}

	// Tail page beyond total => empty, no next_offset, total still reported.
	_, b = agentQuery(t, ts.URL, "/v1/archive/query?project=p&offset=250", "a1", epoch, "sek")
	if got := hitsLen(b); got != 0 {
		t.Fatalf("offset==total must be empty, got %d", got)
	}
	if _, ok := b["next_offset"]; ok {
		t.Fatalf("no page beyond total; next_offset must be absent")
	}
	if tot, _ := num(b, "total"); tot != N {
		t.Fatalf("total must still be %d past the end, got %v", N, b["total"])
	}

	// Malformed params are hard 400s, never a silent default page.
	for _, bad := range []string{"limit=abc", "limit=-1", "offset=xyz", "offset=-5"} {
		if code, _ := agentQuery(t, ts.URL, "/v1/archive/query?project=p&"+bad, "a1", epoch, "sek"); code != http.StatusBadRequest {
			t.Fatalf("%q must be 400, got %d", bad, code)
		}
	}
}

func TestArchiveQueryContinuesMaximumEscapedIdentity(t *testing.T) {
	store := archive.NewMemStore()
	ts, _, _, ctl := captureServer(t, store, nil)
	op := registry.Principal{Kind: registry.Operator}
	if err := ctl.MintProject(op, "p", "fixture"); err != nil {
		t.Fatal(err)
	}
	if _, err := ctl.SetConsent(op, "p", "synthetic", "capture", true); err != nil {
		t.Fatal(err)
	}
	_, grant := do(t, http.MethodPost, ts.URL+"/v1/grants", opHdr(), map[string]any{"principal_id": "wide-reader", "kind": "agent", "projects": []string{"p"}, "ops": []string{"archive.query"}, "secret": "synthetic-secret"})
	epoch := itoa(int64(grant["epoch"].(float64)))
	id := strings.Repeat("\x01", 4096)
	for n := 1; n <= 2; n++ {
		r := archive.Record{Project: "p", Provider: "synthetic", SourceInstance: id, SessionID: id, MessageID: id, Seq: n, Type: archive.TypeMessage, Role: "user", Text: "bounded fixture", ConsentEpoch: 1}
		if n == 2 {
			r.MessageID = strings.Repeat("\x02", 4096)
		}
		if err := store.Put(r); err != nil {
			t.Fatal(err)
		}
	}
	code, first := agentQuery(t, ts.URL, "/v1/archive/query?project=p&limit=1", "wide-reader", epoch, "synthetic-secret")
	cursor, ok := first["next_cursor"].(string)
	if code != 200 || !ok || cursor == "" {
		t.Fatal("first page did not continue", code)
	}
	code, last := agentQuery(t, ts.URL, "/v1/archive/query?project=p&limit=1&cursor="+url.QueryEscape(cursor), "wide-reader", epoch, "synthetic-secret")
	hits, ok := last["hits"].([]any)
	if code != 200 || !ok || len(hits) != 1 {
		t.Fatal("supported escaped identity cursor rejected", code)
	}
	record := hits[0].(map[string]any)
	if record["MessageID"] != strings.Repeat("\x02", 4096) || last["next_cursor"] != nil {
		t.Fatal("cursor repeated or skipped a record")
	}
}
