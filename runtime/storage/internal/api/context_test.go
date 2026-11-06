package api_test

import (
	"aifactory.local/storage/internal/archive"
	"aifactory.local/storage/internal/registry"
	"encoding/json"
	"errors"
	"fmt"
	"net/http"
	"net/url"
	"reflect"
	"strings"
	"testing"
)

func TestArchiveContextFollowsOnlyScopedParents(t *testing.T) {
	store := archive.NewMemStore()
	ts, _, _, ctl := captureServer(t, store, nil)
	op := registry.Principal{ID: "op", Kind: registry.Operator}
	if e := ctl.MintProject(op, "p", "p"); e != nil {
		t.Fatal(e)
	}
	_, g := do(t, http.MethodPost, ts.URL+"/v1/grants", opHdr(), map[string]any{"principal_id": "a1", "kind": "agent", "projects": []string{"p"}, "ops": []string{"archive.query"}, "secret": "sek"})
	epoch := itoa(int64(g["epoch"].(float64)))
	anchor := archive.Record{Project: "p", SourceInstance: "i", SessionID: "s", MessageID: "child", ParentID: "parent", ConsentEpoch: 1, Text: "child"}
	parent := anchor
	parent.MessageID = "parent"
	parent.ParentID = ""
	parent.Text = "parent"
	foreign := parent
	foreign.SourceInstance = "other"
	foreign.Text = "FOREIGN"
	branch := anchor
	branch.MessageID = "branch"
	branch.Text = "BRANCH"
	for _, r := range []archive.Record{anchor, parent, foreign, branch} {
		if e := store.Put(r); e != nil {
			t.Fatal(e)
		}
	}
	path := strings.Replace(messagePath(anchor), "/message?", "/context?", 1)
	code, b := agentQuery(t, ts.URL, path, "a1", epoch, "sek")
	if code != 200 {
		t.Fatal(code, b)
	}
	if b["project"] != "p" || b["derived"] != false || b["order"] != "anchor_to_parent" {
		t.Fatal("wrong context contract", b)
	}
	records := b["records"].([]any)
	if len(records) != 2 || records[0].(map[string]any)["Text"] != "child" || records[1].(map[string]any)["Text"] != "parent" || b["incomplete"] != true || b["stop_reason"] != "no_parent" {
		t.Fatal(b)
	}
}

func TestArchiveContextBoundsAndPrivacy(t *testing.T) {
	for _, scenario := range []string{"limit", "cycle", "missing", "hidden", "anchor-hidden", "backend", "deep-error-hidden", "bytes", "cumulative-bytes", "hidden-bytes", "invalid-limit"} {
		t.Run(scenario, func(t *testing.T) {
			store := &contextStore{MemStore: archive.NewMemStore()}
			ts, _, _, ctl := captureServer(t, store, nil)
			op := registry.Principal{ID: "op", Kind: registry.Operator}
			if e := ctl.MintProject(op, "p", "p"); e != nil {
				t.Fatal(e)
			}
			_, g := do(t, http.MethodPost, ts.URL+"/v1/grants", opHdr(), map[string]any{"principal_id": "a1", "kind": "agent", "projects": []string{"p"}, "ops": []string{"archive.query"}, "secret": "sek"})
			epoch := itoa(int64(g["epoch"].(float64)))
			a := archive.Record{Project: "p", SessionID: "s", MessageID: "a", ParentID: "b", ConsentEpoch: 1}
			b := a
			b.MessageID = "b"
			b.ParentID = "c"
			c := b
			c.MessageID = "c"
			c.ParentID = ""
			want, reason, count := 200, "no_parent", 3
			suffix := ""
			switch scenario {
			case "limit":
				suffix = "&limit=1"
				reason = "limit"
				count = 1
			case "cycle":
				b.ParentID = "a"
				reason = "cycle"
				count = 2
			case "missing":
				b.ParentID = "missing"
				reason = "unavailable"
				count = 2
			case "hidden":
				b.ConsentEpoch = 0
				reason = "unavailable"
				count = 1
			case "anchor-hidden":
				a.ConsentEpoch = 0
				want = 404
			case "backend":
				store.fail = "a"
				want = 503
			case "deep-error-hidden":
				b.ConsentEpoch = 0
				store.fail = "c"
				reason = "unavailable"
				count = 1
			case "bytes":
				a.Text = strings.Repeat("x", archive.ScanBytes)
				reason = "byte_limit"
				count = 0
			case "cumulative-bytes":
				a.Text = strings.Repeat("x", archive.ScanBytes/2)
				b.Text = a.Text
				reason = "byte_limit"
				count = 1
			case "hidden-bytes":
				a.Text = strings.Repeat("x", archive.ScanBytes)
				a.ConsentEpoch = 0
				want = 404
			case "invalid-limit":
				suffix = "&limit=51"
				want = 400
			}
			for _, r := range []archive.Record{a, b, c} {
				if e := store.Put(r); e != nil {
					t.Fatal(e)
				}
			}
			code, body := agentQuery(t, ts.URL, strings.Replace(messagePath(a), "/message?", "/context?", 1)+suffix, "a1", epoch, "sek")
			if code != want {
				t.Fatal(code, body)
			}
			if code == 200 && (len(body["records"].([]any)) != count || body["stop_reason"] != reason || body["incomplete"] != true) {
				t.Fatal(body)
			}
			if scenario == "cumulative-bytes" && store.reads != 2 {
				t.Fatal("read beyond byte budget", store.reads)
			}
			if scenario == "backend" && store.reads != 1 {
				t.Fatal("read after backend error", store.reads)
			}
			if scenario == "missing" && store.reads != 3 {
				t.Fatal("read after absence", store.reads)
			}
			if scenario == "limit" && store.reads != 1 {
				t.Fatal("read beyond limit", store.reads)
			}
			if scenario == "cycle" && store.reads != 2 {
				t.Fatal("read cycle again", store.reads)
			}
			if scenario == "invalid-limit" && store.reads != 0 {
				t.Fatal("read invalid request")
			}
		})
	}
}

type contextStore struct {
	*archive.MemStore
	fail  string
	reads int
}

func (s *contextStore) Lookup(r archive.Record) (archive.Record, bool, error) {
	s.reads++
	if r.MessageID == s.fail {
		r.ParentID = "b"
		return r, true, fmt.Errorf("private backend detail")
	}
	record, found, err := s.MemStore.Lookup(r)
	if !found {
		record.ParentID = "unseen"
	}
	return record, found, err
}

func TestArchiveContextRejectsAmbiguousAndUnboundedIdentity(t *testing.T) {
	ts, _, _, ctl := captureServer(t, archive.NewMemStore(), nil)
	op := registry.Principal{ID: "op", Kind: registry.Operator}
	if err := ctl.MintProject(op, "p", "p"); err != nil {
		t.Fatal(err)
	}
	_, g := do(t, http.MethodPost, ts.URL+"/v1/grants", opHdr(), map[string]any{"principal_id": "a1", "kind": "agent", "projects": []string{"p"}, "ops": []string{"archive.query"}, "secret": "sek"})
	epoch := itoa(int64(g["epoch"].(float64)))
	base := url.Values{"project": {"p"}, "source_instance": {"i"}, "session_id": {"s"}, "message_id": {"m"}}
	for _, key := range []string{"project", "source_instance", "session_id", "message_id"} {
		for _, mode := range []string{"duplicate", "long", "empty"} {
			if key == "source_instance" && mode == "empty" {
				continue
			}
			t.Run(key+"/"+mode, func(t *testing.T) {
				q := url.Values{}
				for k, v := range base {
					q[k] = append([]string{}, v...)
				}
				switch mode {
				case "duplicate":
					q.Add(key, q.Get(key))
				case "long":
					q.Set(key, strings.Repeat("x", 4097))
				case "empty":
					q.Del(key)
				}
				code, _ := agentQuery(t, ts.URL, "/v1/archive/context?"+q.Encode(), "a1", epoch, "sek")
				if code != 400 {
					t.Fatalf("want 400, got %d", code)
				}
			})
		}
	}
}

func TestArchiveContextPrivacyAndFailures(t *testing.T) {
	for _, scenario := range []string{"missing", "not-found-payload", "withheld", "consent", "revoke", "foreign", "search-only", "backend", "blocked", "disabled", "post", "malformed"} {
		t.Run(scenario, func(t *testing.T) {
			store := &messageLookupStore{MemStore: archive.NewMemStore()}
			ts, srv, _, ctl := captureServer(t, store, nil)
			op := registry.Principal{ID: "op", Kind: registry.Operator}
			if e := ctl.MintProject(op, "p", "p"); e != nil {
				t.Fatal(e)
			}
			if _, e := ctl.SetConsent(op, "p", "synthetic", "capture", true); e != nil {
				t.Fatal(e)
			}
			permission := "archive.query"
			if scenario == "search-only" {
				permission = "search"
			}
			_, g := do(t, http.MethodPost, ts.URL+"/v1/grants", opHdr(), map[string]any{"principal_id": "a1", "kind": "agent", "projects": []string{"p"}, "ops": []string{permission}, "secret": "sek"})
			epoch := itoa(int64(g["epoch"].(float64)))
			r := archive.Record{Project: "p", Provider: "synthetic", SourceInstance: "i", SessionID: "s", MessageID: "m", Text: "PRIVATE_CANARY", ConsentEpoch: 1, Type: archive.TypeSummary}
			if scenario != "missing" {
				if e := store.Put(r); e != nil {
					t.Fatal(e)
				}
			}
			want, method, path := 404, http.MethodGet, strings.Replace(messagePath(r), "/message?", "/context?", 1)
			switch scenario {
			case "not-found-payload":
				store.missing = true
			case "withheld":
				store.before = func() { ctl.Retention().DeleteSession("p", "s", 1) }
			case "consent":
				store.before = func() {
					if _, e := ctl.SetConsent(op, "p", "synthetic", "capture", false); e != nil {
						t.Error(e)
					}
				}
			case "revoke":
				want = 403
				store.before = func() {
					code, _ := do(t, http.MethodPost, ts.URL+"/v1/grants/revoke", opHdr(), map[string]string{"principal_id": "a1"})
					if code != 200 {
						t.Error(code)
					}
				}
			case "foreign":
				want = 403
				r.Project = "foreign"
				path = strings.Replace(messagePath(r), "/message?", "/context?", 1)
			case "search-only":
				want = 403
			case "backend":
				want = 503
				store.err = errors.New("PRIVATE_BACKEND_CANARY")
			case "blocked":
				want = 503
				store.before = func() {
					ctl.Close()
					if e := ctl.MintProject(op, "fault", "fault"); e == nil {
						t.Error("expected closed WAL persistence failure")
					}
					if blocked, _ := ctl.Blocked(); !blocked {
						t.Error("fault did not block authority")
					}
				}
			case "disabled":
				want = 503
				srv.SetIngestor(nil)
			case "post":
				want = 405
				method = http.MethodPost
			case "malformed":
				want = 400
				path += "&bad=%ZZ"
			}
			headers := map[string]string{"X-Principal-Id": "a1", "X-Grant-Epoch": epoch, "X-Secret": "sek"}
			code, body := do(t, method, ts.URL+path, headers, nil)
			if code != want {
				t.Fatalf("want %d got %d body=%v", want, code, body)
			}
			raw, _ := json.Marshal(body)
			if strings.Contains(string(raw), "PRIVATE_") {
				t.Fatalf("private data leaked: %s", raw)
			}
			if want == 404 && !reflect.DeepEqual(body, map[string]any{"error": "not_found"}) {
				t.Fatalf("absence/withholding distinguishable: %v", body)
			}
			if scenario == "foreign" || scenario == "search-only" || scenario == "disabled" || scenario == "post" || scenario == "malformed" {
				if store.calls != 0 {
					t.Fatal("lookup before request authorization/validation")
				}
			}
		})
	}
}

func TestArchiveContextRejectsInvalidUTF8(t *testing.T) {
	store := archive.NewMemStore()
	ts, _, _, ctl := captureServer(t, store, nil)
	op := registry.Principal{ID: "op", Kind: registry.Operator}
	if e := ctl.MintProject(op, "p", "p"); e != nil {
		t.Fatal(e)
	}
	_, g := do(t, http.MethodPost, ts.URL+"/v1/grants", opHdr(), map[string]any{"principal_id": "a1", "kind": "agent", "projects": []string{"p"}, "ops": []string{"archive.query"}, "secret": "sek"})
	epoch := itoa(int64(g["epoch"].(float64)))
	r := archive.Record{Project: "p", SourceInstance: "i", SessionID: "s", MessageID: "\ufffd", ConsentEpoch: 1, Text: "replacement character is a real identity"}
	if e := store.Put(r); e != nil {
		t.Fatal(e)
	}
	code, _ := agentQuery(t, ts.URL, strings.Replace(messagePath(r), "/message?", "/context?", 1), "a1", epoch, "sek")
	if code != 200 {
		t.Fatal(code)
	}
	code, _ = agentQuery(t, ts.URL, "/v1/archive/context?project=p&source_instance=i&session_id=s&message_id=%FF", "a1", epoch, "sek")
	if code != 400 {
		t.Fatalf("invalid UTF8 must be rejected: %d", code)
	}
}

func TestArchiveContextLimitContract(t *testing.T) {
	store := &contextStore{MemStore: archive.NewMemStore()}
	ts, _, _, ctl := captureServer(t, store, nil)
	op := registry.Principal{ID: "op", Kind: registry.Operator}
	if e := ctl.MintProject(op, "p", "p"); e != nil {
		t.Fatal(e)
	}
	_, g := do(t, http.MethodPost, ts.URL+"/v1/grants", opHdr(), map[string]any{"principal_id": "a1", "kind": "agent", "projects": []string{"p"}, "ops": []string{"archive.query"}, "secret": "sek"})
	epoch := itoa(int64(g["epoch"].(float64)))
	for n := 0; n < 52; n++ {
		r := archive.Record{Project: "p", SessionID: "s", MessageID: fmt.Sprint(n), ParentID: fmt.Sprint(n + 1), ConsentEpoch: 1}
		if e := store.Put(r); e != nil {
			t.Fatal(e)
		}
	}
	path := "/v1/archive/context?project=p&session_id=s&message_id=0"
	for _, tc := range []struct {
		suffix        string
		status, count int
	}{{"", 200, 10}, {"&limit=50", 200, 50}, {"&limit=0", 400, 0}, {"&limit=-1", 400, 0}, {"&limit=x", 400, 0}, {"&limit=", 400, 0}, {"&limit=1&limit=1", 400, 0}} {
		store.reads = 0
		code, b := agentQuery(t, ts.URL, path+tc.suffix, "a1", epoch, "sek")
		if code != tc.status || store.reads != tc.count {
			t.Fatalf("%s status %d reads %d", tc.suffix, code, store.reads)
		}
		if code == 200 && len(b["records"].([]any)) != tc.count {
			t.Fatal("wrong limit")
		}
	}
}

func TestArchiveContextIdentityBytesAndInclusiveBound(t *testing.T) {
	store := archive.NewMemStore()
	ts, _, _, ctl := captureServer(t, store, nil)
	op := registry.Principal{ID: "op", Kind: registry.Operator}
	if e := ctl.MintProject(op, "p", "p"); e != nil {
		t.Fatal(e)
	}
	_, g := do(t, http.MethodPost, ts.URL+"/v1/grants", opHdr(), map[string]any{"principal_id": "a1", "kind": "agent", "projects": []string{"p"}, "ops": []string{"archive.query"}, "secret": "sek"})
	epoch := itoa(int64(g["epoch"].(float64)))
	for _, id := range []string{"\u00e9", "e\u0301", "A", "a", " a ", strings.Repeat("x", 4096)} {
		r := archive.Record{Project: "p", SessionID: "s", MessageID: id, ConsentEpoch: 1, Text: id}
		if e := store.Put(r); e != nil {
			t.Fatal(e)
		}
	}
	for _, id := range []string{"\u00e9", "e\u0301", "A", "a", " a ", strings.Repeat("x", 4096)} {
		path := "/v1/archive/context?" + url.Values{"project": {"p"}, "session_id": {"s"}, "message_id": {id}}.Encode()
		code, b := agentQuery(t, ts.URL, path, "a1", epoch, "sek")
		if code != 200 {
			t.Fatalf("exact/omitted source lookup %d", code)
		}
		if b["records"].([]any)[0].(map[string]any)["Text"] != id {
			t.Fatal("identity normalized or trimmed")
		}
	}
}
