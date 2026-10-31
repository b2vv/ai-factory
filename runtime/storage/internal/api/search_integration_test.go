//go:build integration

package api_test

import (
	"aifactory.local/storage/internal/archive"
	"aifactory.local/storage/internal/config"
	"aifactory.local/storage/internal/registry"
	"aifactory.local/storage/internal/search"
	"context"
	"fmt"
	"net/http"
	"net/url"
	"os"
	"testing"
	"time"
)

func TestDerivedIndexLifecyclePrivacyRebuildAndPGFailure(t *testing.T) {
	dsn := os.Getenv("PG_DSN")
	if dsn == "" {
		t.Skip("PG_DSN unavailable")
	}
	open := func() *search.Store {
		ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
		defer cancel()
		s, e := search.Open(ctx, dsn)
		if e != nil {
			t.Fatal(e)
		}
		t.Cleanup(s.Close)
		return s
	}
	idx := open()
	project := fmt.Sprintf("index_api_%d", time.Now().UnixNano())
	defer idx.Purge(project)
	store := archive.NewMemStore()
	ts, s, ing, ctl := captureServer(t, store, nil)
	s.SetSearchStore(idx)
	op := registry.Principal{ID: "op", Kind: registry.Operator}
	if e := ctl.MintProject(op, project, project); e != nil {
		t.Fatal(e)
	}
	if _, e := ctl.SetConsent(op, project, "synthetic", "capture", true); e != nil {
		t.Fatal(e)
	}
	_, grant := do(t, http.MethodPost, ts.URL+"/v1/grants", opHdr(), map[string]any{"principal_id": "index-agent", "kind": "agent", "projects": []string{project}, "ops": []string{"archive.query", "search"}, "secret": "synthetic-index"})
	epoch := itoa(int64(grant["epoch"].(float64)))
	query := func(path string) (int, map[string]any) {
		return agentQuery(t, ts.URL, path, "index-agent", epoch, "synthetic-index")
	}
	records := []archive.Record{}
	for n := 0; n < 20; n++ {
		r := archive.Record{Project: project, Provider: "synthetic", SourceInstance: "i", SessionID: "s", MessageID: fmt.Sprint(n), Seq: n, Type: archive.TypeMessage, Role: "user", Text: "searchable source", ConsentEpoch: 1}
		records = append(records, r)
		key := archive.IdentityKey(r)
		if n == 0 {
			key = "legacy-index-alias"
		}
		if _, e := ing.Accept(key, r, config.Usage{FreeBytes: 1 << 40}); e != nil {
			t.Fatal(e)
		}
	}
	if n, e := s.DrainOnce(); e != nil || n != 20 {
		t.Fatal(n, e)
	}
	receipt := func(key string) map[string]any {
		code, b := query("/v1/ingest/" + url.PathEscape(key) + "?project=" + project)
		if code != 200 {
			t.Fatal(code, b)
		}
		return b
	}
	if b := receipt("legacy-index-alias"); b["state"] != "archive_committed" || b["index_state"] != "pending" {
		t.Fatal(b)
	}
	if n, e := s.IndexOnce(); e != nil || n != 16 {
		t.Fatal("bounded first index", n, e)
	}
	if b := receipt("legacy-index-alias"); b["state"] != "indexed" {
		t.Fatal(b)
	}
	if n, e := s.IndexOnce(); e != nil || n != 4 {
		t.Fatal("bounded continuation", n, e)
	}
	code, b := query("/v1/search/query?project=" + project + "&q=searchable")
	if code != 200 || len(b["hits"].([]any)) != 20 {
		t.Fatal(code, b)
	}
	if code, _ := query("/v1/search/query?project=foreign"); code != 403 {
		t.Fatal("cross project", code)
	}
	if e := idx.Purge(project); e != nil {
		t.Fatal(e)
	}
	if b := receipt(archive.IdentityKey(records[0])); b["state"] != "archive_committed" {
		t.Fatal("drop must invalidate indexed status", b)
	}
	s.SetSearchStore(idx)
	for n := 0; n < 2; n++ {
		if _, e := s.IndexOnce(); e != nil {
			t.Fatal(e)
		}
	}
	code, b = query("/v1/search/query?project=" + project + "&q=searchable")
	if code != 200 || len(b["hits"].([]any)) != 20 {
		t.Fatal("rebuild differs", code, b)
	}
	// A PG outage does not retract an actual archive commit or delay new drains.
	idx.Close()
	if b := receipt(archive.IdentityKey(records[0])); b["state"] != "archive_committed" || b["index_state"] != "unavailable" {
		t.Fatal(b)
	}
	r := records[0]
	r.MessageID = "after-index-down"
	r.Seq = 21
	if _, e := ing.Accept(archive.IdentityKey(r), r, config.Usage{FreeBytes: 1 << 40}); e != nil {
		t.Fatal(e)
	}
	if n, e := s.DrainOnce(); e != nil || n != 1 {
		t.Fatal("PG held archive commit", n, e)
	}
	idx = open()
	s.SetSearchStore(idx)
	if _, e := ctl.SetConsent(op, project, "synthetic", "capture", false); e != nil {
		t.Fatal(e)
	}
	code, b = query("/v1/search/query?project=" + project + "&q=searchable")
	if code != 200 || len(b["hits"].([]any)) != 0 {
		t.Fatal("stale index leaked revoked source", code, b)
	}
	if code, _ := do(t, http.MethodPost, ts.URL+"/v1/barriers/project", opHdr(), map[string]string{"Project": project}); code != 200 {
		t.Fatal(code)
	}
	if code, b := do(t, http.MethodPost, ts.URL+"/v1/purge/project", opHdr(), map[string]string{"Project": project}); code != 200 || b["complete"] != true {
		t.Fatal(code, b)
	}
	refs, _, e := idx.Window(project, "", "")
	if e != nil || len(refs) != 0 {
		t.Fatal("index bytes not purged", refs, e)
	}
}

func TestDerivedIndexEncryptedContinuationAcrossWithheldWindow(t *testing.T) {
	dsn := os.Getenv("PG_DSN")
	if dsn == "" {
		t.Skip("PG_DSN unavailable")
	}
	idx, e := search.Open(context.Background(), dsn)
	if e != nil {
		t.Fatal(e)
	}
	defer idx.Close()
	project := fmt.Sprintf("cursor_api_%d", time.Now().UnixNano())
	defer idx.Purge(project)
	store := archive.NewMemStore()
	ts, s, _, ctl := captureServer(t, store, nil)
	s.SetSearchStore(idx)
	op := registry.Principal{ID: "op", Kind: registry.Operator}
	if e := ctl.MintProject(op, project, project); e != nil {
		t.Fatal(e)
	}
	if _, e := ctl.SetConsent(op, project, "synthetic", "capture", true); e != nil {
		t.Fatal(e)
	}
	_, grant := do(t, http.MethodPost, ts.URL+"/v1/grants", opHdr(), map[string]any{"principal_id": "cursor-agent", "kind": "agent", "projects": []string{project}, "ops": []string{"search"}, "secret": "synthetic-cursor"})
	query := func(path string) (int, map[string]any) {
		return agentQuery(t, ts.URL, path, "cursor-agent", itoa(int64(grant["epoch"].(float64))), "synthetic-cursor")
	}
	for n := 0; n < 101; n++ {
		r := archive.Record{Project: project, Provider: "synthetic", SourceInstance: "i", SessionID: "s", MessageID: fmt.Sprint(n), Seq: n, Type: archive.TypeMessage, Role: "user", Text: "needle", ConsentEpoch: 1}
		if e := store.Put(r); e != nil {
			t.Fatal(e)
		}
		if e := idx.Put(r); e != nil {
			t.Fatal(e)
		}
	}
	path := "/v1/search/query?project=" + project + "&q=needle"
	code, b := query(path)
	if code != 200 || len(b["hits"].([]any)) != 100 {
		t.Fatal(code, b)
	}
	cursor, ok := b["next_cursor"].(string)
	if !ok || cursor == "" {
		t.Fatal("missing encrypted continuation", b)
	}
	if _, ok := b["next_after"]; ok {
		t.Fatal("raw index identity exposed")
	}
	if _, ok := b["total"]; ok {
		t.Fatal("raw total exposed")
	}
	code, b = query(path + "&cursor=" + url.QueryEscape(cursor))
	if code != 200 || len(b["hits"].([]any)) != 1 || b["next_cursor"] != "" {
		t.Fatal(code, b)
	}
	for _, bad := range []string{path + "x&cursor=" + url.QueryEscape(cursor), "/v1/documents/query?project=" + project + "&cursor=" + url.QueryEscape(cursor), path + "&after=" + fmt.Sprintf("%064d", 0), path + "&cursor=malformed"} {
		if code, b := query(bad); code != 400 {
			t.Fatal("cursor scope", code, b)
		}
	}
	if _, e := ctl.SetConsent(op, project, "synthetic", "capture", false); e != nil {
		t.Fatal(e)
	}
	code, b = query(path)
	if code != 200 || len(b["hits"].([]any)) != 0 || b["next_cursor"] == "" {
		t.Fatal("withheld window", code, b)
	}
	code, b = query(path + "&cursor=" + url.QueryEscape(b["next_cursor"].(string)))
	if code != 200 || len(b["hits"].([]any)) != 0 || b["next_cursor"] != "" {
		t.Fatal("withheld continuation", code, b)
	}
}
