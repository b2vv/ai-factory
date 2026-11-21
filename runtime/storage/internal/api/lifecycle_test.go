package api_test

import (
	"aifactory.local/storage/internal/archive"
	"aifactory.local/storage/internal/config"
	"aifactory.local/storage/internal/registry"
	"net/http"
	"net/url"
	"sync/atomic"
	"testing"
	"time"
)

func TestRequestPendingFailureThenDurableAndCancellation(t *testing.T) {
	entered := make(chan struct{})
	resume := make(chan struct{})
	var called atomic.Bool
	meter := func() (config.Usage, error) {
		if !called.Swap(true) {
			close(entered)
			<-resume
			return config.Usage{}, nil
		}
		return config.Usage{FreeBytes: 1 << 40}, nil
	}
	ts, _, _, ctl := captureServer(t, archive.NewMemStore(), meter)
	t.Cleanup(func() {
		select {
		case <-resume:
		default:
			close(resume)
		}
	})
	op := registry.Principal{ID: "op", Kind: registry.Operator}
	ctl.MintProject(op, "p", "p")
	ctl.SetConsent(op, "p", "synthetic", "capture", true)
	_, grant := do(t, http.MethodPost, ts.URL+"/v1/grants", opHdr(), map[string]any{"principal_id": "a", "kind": "agent", "projects": []string{"p"}, "ops": []string{"archive.query"}, "secret": "synthetic"})
	epoch := itoa(int64(grant["epoch"].(float64)))
	r := archive.Record{Project: "p", SourceInstance: "i", SessionID: "s", MessageID: "m"}
	key := archive.IdentityKey(r)
	read := func() map[string]any {
		code, b := agentQuery(t, ts.URL, "/v1/ingest/"+url.PathEscape(key)+"?project=p", "a", epoch, "synthetic")
		if code != 200 {
			t.Fatal(code, b)
		}
		return b
	}
	body := map[string]any{"project": "p", "provider": "synthetic", "source_instance": "i", "messages": []map[string]any{{"session_id": "s", "message_id": "m", "seq": 1, "kind": "message", "role": "user", "text": "synthetic"}}}
	done := make(chan int, 1)
	go func() { code, _ := do(t, http.MethodPost, ts.URL+"/v1/capture", opHdr(), body); done <- code }()
	select {
	case <-entered:
	case <-time.After(3 * time.Second):
		t.Fatal("meter not reached")
	}
	if b := read(); b["lifecycle_state"] != "pending" || b["observation"] != "ephemeral_request_10m" {
		t.Fatal(b)
	}
	close(resume)
	select {
	case code := <-done:
		if code != 503 {
			t.Fatal(code)
		}
	case <-time.After(3 * time.Second):
		t.Fatal("capture not bounded")
	}
	if b := read(); b["lifecycle_state"] != "failed" {
		t.Fatal(b)
	}
	if code, b := do(t, http.MethodPost, ts.URL+"/v1/capture", opHdr(), body); code != 200 {
		t.Fatal(code, b)
	}
	if b := read(); b["lifecycle_state"] != "archive_committed" || b["observation"] != nil {
		t.Fatal("ephemeral failure overrode durable proof", b)
	}
	ctl.SetConsent(op, "p", "synthetic", "capture", false)
	if b := read(); b["lifecycle_state"] != "cancelled" {
		t.Fatal("revocation not reflected", b)
	}
}
