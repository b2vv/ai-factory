package api_test

// Regression tests from the Codex review (R1/R5/R6), kept as permanent safety assertions.

import (
	"errors"
	"net/http"
	"net/http/httptest"
	"path/filepath"
	"testing"

	"aifactory.local/storage/internal/api"
	"aifactory.local/storage/internal/archive"
	"aifactory.local/storage/internal/config"
	"aifactory.local/storage/internal/control"
	"aifactory.local/storage/internal/ingest"
	"aifactory.local/storage/internal/registry"
)

// captureServer builds a real API server with capture enabled over the given store, returning
// the http test server, the *api.Server (to call DrainOnce directly), the ingestor and ctl.
func captureServer(t *testing.T, store archive.Store, meter func() (config.Usage, error)) (*httptest.Server, *api.Server, *ingest.Ingestor, *control.Durable) {
	t.Helper()
	d := t.TempDir()
	ictl, err := control.Initialize(filepath.Join(d, "ctl"))
	if err != nil {
		t.Fatal(err)
	}
	ictl.Close() // release the init flock before reopening for serving
	ctl, err := control.Open(filepath.Join(d, "ctl"))
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { ctl.Close() })
	i, err := ingest.Open(filepath.Join(d, "ing"), config.NewAccountant(config.Default()), store)
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { i.Close() })
	c := config.Default()
	c.CaptureEnabled = true
	srv := api.New(ctl, c, "op", opSecret)
	srv.SetIngestor(i)
	srv.SetAvailability(store.Available, nil)
	if meter == nil {
		meter = func() (config.Usage, error) { return config.Usage{FreeBytes: 1 << 40}, nil }
	}
	srv.SetUsageMeter(meter)
	ts := httptest.NewServer(srv.Handler())
	t.Cleanup(ts.Close)
	return ts, srv, i, ctl
}

// errStore is Available() but every Fetch returns a read error (R6): a backend failure AFTER
// the availability check, or a read timeout.
type errStore struct{ archive.MemStore }

func newErrStore() *errStore { return &errStore{MemStore: *archive.NewMemStore()} }
func (s *errStore) Fetch(string) ([]archive.Record, error) {
	return nil, errors.New("simulated mongo read error")
}

// R6: a concrete archive read error must surface as 503, NOT a 200 with empty hits.
func TestReviewArchiveReadErrorIsUnavailableNotEmpty(t *testing.T) {
	ts, _, _, _ := captureServer(t, newErrStore(), nil)
	if code, _ := do(t, http.MethodPost, ts.URL+"/v1/projects", opHdr(), map[string]string{"UUID": "p", "Label": "p"}); code != 201 {
		t.Fatalf("mint: %d", code)
	}
	_, gm := do(t, http.MethodPost, ts.URL+"/v1/grants", opHdr(), map[string]any{"principal_id": "a1", "kind": "agent", "projects": []string{"p"}, "ops": []string{"archive.query"}, "secret": "sek"})
	epoch := int64(gm["epoch"].(float64))
	req, _ := http.NewRequest(http.MethodGet, ts.URL+"/v1/archive/query?project=p", nil)
	req.Header.Set("X-Principal-Id", "a1")
	req.Header.Set("X-Grant-Epoch", itoa(epoch))
	req.Header.Set("X-Secret", "sek")
	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		t.Fatal(err)
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusServiceUnavailable {
		t.Fatalf("archive read error must be 503, got %d", resp.StatusCode)
	}
}

// R5: a record accepted while the archive is DOWN is projected by the server's background-drain
// entry point (DrainOnce) on recovery, WITHOUT any new capture request.
func TestReviewDrainOnceReplaysWithoutNewCapture(t *testing.T) {
	store := archive.NewMemStore()
	ts, srv, ing, ctl := captureServer(t, store, nil)
	op := registry.Principal{ID: "op", Kind: registry.Operator}
	ctl.MintProject(op, "p", "p")
	ctl.SetConsent(op, "p", "synthetic", "capture", true)

	// Accept directly into the WAL while the archive is down (buffered, not published).
	store.SetAvailable(false)
	if _, err := ing.Accept("k", archive.Record{Project: "p", Provider: "synthetic", SourceInstance: "i", SessionID: "s", MessageID: "m", Type: archive.TypeMessage, Role: "user", Text: "queued", ConsentEpoch: 1}, config.Usage{FreeBytes: 1 << 40}); err != nil {
		t.Fatal(err)
	}
	if n, err := srv.DrainOnce(); err == nil || n != 0 {
		t.Fatalf("drain while archive down must fail closed, got n=%d err=%v", n, err)
	}
	// Recovery: DrainOnce (the worker's entry point) projects the queued record — no new capture.
	store.SetAvailable(true)
	n, err := srv.DrainOnce()
	if err != nil || n != 1 {
		t.Fatalf("recovery DrainOnce must project the queued record without a new capture: n=%d err=%v", n, err)
	}
	if len(store.All("p")) != 1 {
		t.Fatalf("queued record must be archived after recovery")
	}
	_ = ts
}

// R1 (kept from the Codex probe): a capture that is paused in the usage meter (gate already
// read, barrier not yet set) must NOT restore a payload after a purge completes. With the fix
// (meter measured before the lock; gate RE-CHECKED under the lock) the resumed capture observes
// the barrier and refuses, so no WAL payload survives the purge.
func TestReviewPurgeThenInflightCapture(t *testing.T) {
	d := t.TempDir()
	ictl, e := control.Initialize(filepath.Join(d, "ctl"))
	if e != nil {
		t.Fatal(e)
	}
	ictl.Close()
	ctl, e := control.Open(filepath.Join(d, "ctl"))
	if e != nil {
		t.Fatal(e)
	}
	defer ctl.Close()
	o := registry.Principal{ID: "op", Kind: registry.Operator}
	ctl.MintProject(o, "p", "p")
	ctl.SetConsent(o, "p", "synthetic", "capture", true)
	s := archive.NewMemStore()
	i, e := ingest.Open(filepath.Join(d, "ing"), config.NewAccountant(config.Default()), s)
	if e != nil {
		t.Fatal(e)
	}
	defer i.Close()
	c := config.Default()
	c.CaptureEnabled = true
	srv := api.New(ctl, c, "op", opSecret)
	srv.SetIngestor(i)
	srv.SetAvailability(s.Available, nil)
	entered := make(chan struct{})
	resume := make(chan struct{})
	srv.SetUsageMeter(func() (config.Usage, error) { close(entered); <-resume; return config.Usage{FreeBytes: 1 << 40}, nil })
	ts := httptest.NewServer(srv.Handler())
	defer ts.Close()
	done := make(chan struct{})
	go func() {
		defer close(done)
		do(t, http.MethodPost, ts.URL+"/v1/capture", opHdr(), map[string]any{"project": "p", "provider": "synthetic", "source_instance": "i", "messages": []map[string]any{{"session_id": "s", "message_id": "m", "text": "should be erased"}}})
	}()
	<-entered
	ctl.DeleteProjectBarrier(o, "p")
	code, m := do(t, http.MethodPost, ts.URL+"/v1/purge/project", opHdr(), map[string]string{"Project": "p"})
	close(resume)
	<-done
	if code != 200 || m["complete"] != true {
		t.Fatalf("unexpected purge %d %v", code, m)
	}
	n, e := i.AcceptedCount()
	if e != nil {
		t.Fatal(e)
	}
	if n != 0 {
		t.Fatalf("purge complete=true but paused pre-barrier capture restored %d WAL payload(s)", n)
	}
}

func itoa(n int64) string {
	if n == 0 {
		return "0"
	}
	var b []byte
	for n > 0 {
		b = append([]byte{byte('0' + n%10)}, b...)
		n /= 10
	}
	return string(b)
}

func (s *errStore) Scan(string, *archive.Position) (archive.Window, error) {
	return archive.Window{}, errors.New("injected read error")
}
