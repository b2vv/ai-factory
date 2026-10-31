package api_test

import (
	"aifactory.local/storage/internal/archive"
	"aifactory.local/storage/internal/registry"
	"net/http"
	"testing"
)

type alternatingV9 struct {
	*archive.MemStore
	calls int
}

func (s *alternatingV9) Fetch(p string) ([]archive.Record, error) {
	r, e := s.MemStore.Fetch(p)
	s.calls++
	if s.calls%2 == 0 {
		for a, b := 0, len(r)-1; a < b; a, b = a+1, b-1 {
			r[a], r[b] = r[b], r[a]
		}
	}
	return r, e
}
func TestReviewerV9StablePaginationTies(t *testing.T) {
	store := &alternatingV9{MemStore: archive.NewMemStore()}
	ts, _, _, ctl := captureServer(t, store, nil)
	op := registry.Principal{ID: "op", Kind: registry.Operator}
	ctl.MintProject(op, "p", "p")
	ctl.SetConsent(op, "p", "synthetic", "capture", true)
	_, g := do(t, http.MethodPost, ts.URL+"/v1/grants", opHdr(), map[string]any{"principal_id": "a1", "kind": "agent", "projects": []string{"p"}, "ops": []string{"archive.query"}, "secret": "sek"})
	ep := itoa(int64(g["epoch"].(float64)))
	for _, source := range []string{"one", "two"} {
		store.Put(archive.Record{Project: "p", Provider: "synthetic", SourceInstance: source, SessionID: "s", MessageID: "m", Seq: 1, ConsentEpoch: 1})
	}
	get := func(off string) string {
		code, b := agentQuery(t, ts.URL, "/v1/archive/query?project=p&limit=1&offset="+off, "a1", ep, "sek")
		if code != 200 {
			t.Fatal(code, b)
		}
		return b["hits"].([]any)[0].(map[string]any)["SourceInstance"].(string)
	}
	a, b := get("0"), get("1")
	if a == b {
		t.Fatalf("unchanged dataset page walk duplicates %q and skips other source", a)
	}
}
func TestReviewerV9FilteringBeforePagination(t *testing.T) {
	s := archive.NewMemStore()
	ts, _, _, ctl := captureServer(t, s, nil)
	op := registry.Principal{ID: "op", Kind: registry.Operator}
	ctl.MintProject(op, "p", "p")
	ctl.SetConsent(op, "p", "synthetic", "capture", true)
	_, g := do(t, http.MethodPost, ts.URL+"/v1/grants", opHdr(), map[string]any{"principal_id": "a1", "kind": "agent", "projects": []string{"p"}, "ops": []string{"archive.query"}, "secret": "sek"})
	ep := itoa(int64(g["epoch"].(float64)))
	for _, sess := range []string{"hidden", "visible"} {
		s.Put(archive.Record{Project: "p", Provider: "synthetic", SourceInstance: "i", SessionID: sess, MessageID: "m", ConsentEpoch: 1})
	}
	ctl.Retention().DeleteSession("p", "hidden", 1)
	code, b := agentQuery(t, ts.URL, "/v1/archive/query?project=p&limit=1", "a1", ep, "sek")
	if code != 200 || b["total"] != float64(1) {
		t.Fatal(code, b)
	}
	if _, ok := b["next_offset"]; ok {
		t.Fatal("withheld count leaked", b)
	}
	if b["hits"].([]any)[0].(map[string]any)["SessionID"] != "visible" {
		t.Fatal(b)
	}
}
