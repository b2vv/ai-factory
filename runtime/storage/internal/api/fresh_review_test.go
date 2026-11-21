package api_test

import (
	"aifactory.local/storage/internal/api"
	"aifactory.local/storage/internal/archive"
	"aifactory.local/storage/internal/config"
	"aifactory.local/storage/internal/control"
	"aifactory.local/storage/internal/ingest"
	"aifactory.local/storage/internal/registry"
	"net/http"
	"net/url"
	"os"
	"path/filepath"
	"sync"
	"testing"
)

func TestFreshBlockedAuthorityMustNotTerminallyQuarantine(t *testing.T) {
	dir := t.TempDir()
	cp := filepath.Join(dir, "control")
	ip := filepath.Join(dir, "ingest")
	d, e := control.Initialize(cp)
	if e != nil {
		t.Fatal(e)
	}
	op := registry.Principal{ID: "op", Kind: registry.Operator}
	if e = d.MintProject(op, "p", "p"); e != nil {
		t.Fatal(e)
	}
	if _, e = d.SetConsent(op, "p", "synthetic", "capture", true); e != nil {
		t.Fatal(e)
	}
	store := archive.NewMemStore()
	cfg := config.Default()
	cfg.CaptureEnabled = true
	i, e := ingest.Open(ip, config.NewAccountant(cfg), store)
	if e != nil {
		t.Fatal(e)
	}
	r := archive.Record{Project: "p", Provider: "synthetic", SourceInstance: "i", SessionID: "s", MessageID: "m", ConsentEpoch: 1, Text: "accepted backlog"}
	key := archive.IdentityKey(r)
	if _, e = i.Accept(key, r, config.Usage{FreeBytes: 1 << 40}); e != nil {
		t.Fatal(e)
	}
	if e = os.Mkdir(filepath.Join(cp, "control.meta.tmp"), 0700); e != nil {
		t.Fatal(e)
	}
	if e = d.MintProject(op, "unrelated", "unrelated"); e == nil {
		t.Fatal("fault not triggered")
	}
	s := api.New(d, cfg, "op", opSecret)
	s.SetIngestor(i)
	n, de := s.DrainOnce()
	t.Logf("blocked drain n=%d err=%v", n, de)
	if len(store.All("p")) != 0 {
		t.Fatal("published while blocked")
	}
	i.Close()
	d.Close()
	if e = os.Remove(filepath.Join(cp, "control.meta.tmp")); e != nil {
		t.Fatal(e)
	}
	d, e = control.Open(cp)
	if e != nil {
		t.Fatal(e)
	}
	defer d.Close()
	i, e = ingest.Open(ip, config.NewAccountant(cfg), store)
	if e != nil {
		t.Fatal(e)
	}
	defer i.Close()
	if b, w := d.Blocked(); b {
		t.Fatal(w)
	}
	s = api.New(d, cfg, "op", opSecret)
	s.SetIngestor(i)
	n, e = s.DrainOnce()
	st, se := i.RecordState(key, "p")
	t.Logf("recovered n=%d err=%v receipt=%+v err=%v", n, e, st, se)
	if n != 1 || e != nil {
		t.Fatalf("authorized accepted backlog never published after recovery: n=%d err=%v state=%s", n, e, st.State)
	}
}

type freshSlowLookup struct {
	*archive.MemStore
	entered, release chan struct{}
	once             sync.Once
}

func (s *freshSlowLookup) Lookup(r archive.Record) (archive.Record, bool, error) {
	s.once.Do(func() { close(s.entered) })
	<-s.release
	return s.MemStore.Lookup(r)
}
func TestFreshReceiptRechecksRevokedGrantAfterIO(t *testing.T) {
	store := &freshSlowLookup{MemStore: archive.NewMemStore(), entered: make(chan struct{}), release: make(chan struct{})}
	ts, _, i, d := captureServer(t, store, nil)
	op := registry.Principal{ID: "op", Kind: registry.Operator}
	if e := d.MintProject(op, "p", "p"); e != nil {
		t.Fatal(e)
	}
	_, g := do(t, http.MethodPost, ts.URL+"/v1/grants", opHdr(), map[string]any{"principal_id": "a1", "kind": "agent", "projects": []string{"p"}, "ops": []string{"archive.query"}, "secret": "sek"})
	ep := itoa(int64(g["epoch"].(float64)))
	r := archive.Record{Project: "p", SourceInstance: "i", SessionID: "s", MessageID: "m"}
	key := archive.IdentityKey(r)
	if _, e := i.Accept(key, r, config.Usage{FreeBytes: 1 << 40}); e != nil {
		t.Fatal(e)
	}
	if _, e := i.Drain(); e != nil {
		t.Fatal(e)
	}
	done := make(chan int, 1)
	go func() {
		code, _ := agentQuery(t, ts.URL, "/v1/ingest/"+url.PathEscape(key)+"?project=p", "a1", ep, "sek")
		done <- code
	}()
	<-store.entered
	code, _ := do(t, http.MethodPost, ts.URL+"/v1/grants/revoke", opHdr(), map[string]string{"principal_id": "a1"})
	if code != 200 {
		t.Fatal(code)
	}
	close(store.release)
	code = <-done
	if code != 403 {
		t.Fatalf("receipt returned %d after completed grant revocation; expected 403", code)
	}
}
