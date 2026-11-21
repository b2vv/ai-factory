package api_test

import (
	"encoding/json"
	"errors"
	"net/http"
	"net/url"
	"reflect"
	"strings"
	"testing"

	"aifactory.local/storage/internal/archive"
	"aifactory.local/storage/internal/registry"
)

func messagePath(r archive.Record) string {
	return "/v1/archive/message?" + url.Values{"project": {r.Project}, "source_instance": {r.SourceInstance}, "session_id": {r.SessionID}, "message_id": {r.MessageID}}.Encode()
}

func TestArchiveMessageExactSourceIdentity(t *testing.T) {
	store := archive.NewMemStore()
	ts, _, _, ctl := captureServer(t, store, nil)
	op := registry.Principal{ID: "op", Kind: registry.Operator}
	if err := ctl.MintProject(op, "p", "p"); err != nil {
		t.Fatal(err)
	}
	if _, err := ctl.SetConsent(op, "p", "synthetic", "capture", true); err != nil {
		t.Fatal(err)
	}
	_, grant := do(t, http.MethodPost, ts.URL+"/v1/grants", opHdr(), map[string]any{"principal_id": "a1", "kind": "agent", "projects": []string{"p"}, "ops": []string{"archive.query"}, "secret": "sek"})
	epoch := itoa(int64(grant["epoch"].(float64)))
	for _, source := range []string{"", "source-a", "source-b"} {
		want := archive.Record{Project: "p", Provider: "synthetic", SourceInstance: source, SessionID: "s/\u00e9", MessageID: "m?\u03b1", ParentID: "parent", Seq: 7, Type: archive.TypeMessage, Role: "user", Text: "original \u00e9 " + source, ConsentEpoch: 1}
		if err := store.Put(want); err != nil {
			t.Fatal(err)
		}
		code, body := agentQuery(t, ts.URL, messagePath(want), "a1", epoch, "sek")
		if code != 200 {
			t.Fatalf("fetch status=%d body=%v", code, body)
		}
		raw, _ := json.Marshal(body["record"])
		var got archive.Record
		if err := json.Unmarshal(raw, &got); err != nil {
			t.Fatal(err)
		}
		if !reflect.DeepEqual(got, want) || body["project"] != "p" || body["derived"] != false {
			t.Fatalf("not unchanged authoritative record: %+v %v", got, body)
		}
	}
}

func TestArchiveMessageRejectsAmbiguousAndUnboundedIdentity(t *testing.T) {
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
				code, _ := agentQuery(t, ts.URL, "/v1/archive/message?"+q.Encode(), "a1", epoch, "sek")
				if code != 400 {
					t.Fatalf("want 400, got %d", code)
				}
			})
		}
	}
}

type messageLookupStore struct {
	*archive.MemStore
	before  func()
	err     error
	calls   int
	missing bool
}

func (s *messageLookupStore) Lookup(r archive.Record) (archive.Record, bool, error) {
	s.calls++
	if s.before != nil {
		s.before()
	}
	if s.err != nil {
		return archive.Record{}, false, s.err
	}
	record, found, err := s.MemStore.Lookup(r)
	if s.missing {
		found = false
	}
	return record, found, err
}

func TestArchiveMessagePrivacyAndFailures(t *testing.T) {
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
			want, method, path := 404, http.MethodGet, messagePath(r)
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
				path = messagePath(r)
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

func TestArchiveMessageRejectsInvalidUTF8(t *testing.T) {
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
	code, _ := agentQuery(t, ts.URL, messagePath(r), "a1", epoch, "sek")
	if code != 200 {
		t.Fatal(code)
	}
	code, _ = agentQuery(t, ts.URL, "/v1/archive/message?project=p&source_instance=i&session_id=s&message_id=%FF", "a1", epoch, "sek")
	if code != 400 {
		t.Fatalf("invalid UTF8 must be rejected: %d", code)
	}
}

func TestArchiveMessageIdentityBytesAndInclusiveBound(t *testing.T) {
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
		path := "/v1/archive/message?" + url.Values{"project": {"p"}, "session_id": {"s"}, "message_id": {id}}.Encode()
		code, b := agentQuery(t, ts.URL, path, "a1", epoch, "sek")
		if code != 200 {
			t.Fatalf("exact/omitted source lookup %d", code)
		}
		if b["record"].(map[string]any)["Text"] != id {
			t.Fatal("identity normalized or trimmed")
		}
	}
}
