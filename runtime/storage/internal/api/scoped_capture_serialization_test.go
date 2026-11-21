package api_test

import (
	"aifactory.local/storage/internal/archive"
	"aifactory.local/storage/internal/registry"
	"sync"
	"testing"
	"time"
)

type blockedCaptureStore struct {
	*archive.MemStore
	entered chan struct{}
	release chan struct{}
	once    sync.Once
}

func (s *blockedCaptureStore) block()                     { s.once.Do(func() { close(s.entered); <-s.release }) }
func (s *blockedCaptureStore) Put(r archive.Record) error { s.block(); return s.MemStore.Put(r) }
func (s *blockedCaptureStore) PutEnvelope(e archive.Envelope) error {
	s.block()
	return s.MemStore.PutEnvelope(e)
}
func TestScopedCaptureSerializesRevokeWithAcceptance(t *testing.T) {
	for _, metadata := range []bool{false, true} {
		name := "legacy"
		if metadata {
			name = "v2"
		}
		t.Run(name, func(t *testing.T) {
			source := &blockedCaptureStore{MemStore: archive.NewMemStore(), entered: make(chan struct{}), release: make(chan struct{})}
			var release sync.Once
			defer release.Do(func() { close(source.release) })
			f := scopedFixture(t, metadata, nil, source)
			response := make(chan int, 1)
			go func() { code, _ := scopedRequest(t, f, "generic", "p", f.writer); response <- code }()
			select {
			case <-source.entered:
			case <-time.After(10 * time.Second):
				t.Fatal("capture never reached blocking source")
			}
			started := make(chan struct{})
			revoked := make(chan error, 1)
			go func() {
				close(started)
				revoked <- f.ctl.RevokeGrant(registry.Principal{Kind: registry.Operator}, "writer")
			}()
			<-started
			select {
			case e := <-revoked:
				t.Fatal("revoke crossed active writer fence", e)
			case <-time.After(100 * time.Millisecond):
			}
			release.Do(func() { close(source.release) })
			select {
			case code := <-response:
				if code != 200 {
					t.Fatal("authorized acceptance failed", code)
				}
			case <-time.After(10 * time.Second):
				t.Fatal("capture deadlock")
			}
			select {
			case e := <-revoked:
				if e != nil {
					t.Fatal(e)
				}
			case <-time.After(10 * time.Second):
				t.Fatal("revoke deadlock")
			}
			if code, _ := scopedRequest(t, f, "generic", "p", f.writer); code != 403 {
				t.Fatal("post-revoke replay accepted", code)
			}
			p, e := f.ing.Progress()
			if e != nil || p.Accepted != 1 {
				t.Fatal("durable acceptance count", p, e)
			}
		})
	}
}

func TestScopedCaptureRetainsOnlyAuthorizedBatchPrefix(t *testing.T) {
	for _, metadata := range []bool{false, true} {
		name := "legacy"
		if metadata {
			name = "v2"
		}
		t.Run(name, func(t *testing.T) {
			f := scopedFixture(t, metadata, nil)
			if _, e := f.ctl.DeleteSessionBarrier(registry.Principal{Kind: registry.Operator}, "p", "deleted"); e != nil {
				t.Fatal(e)
			}
			body := map[string]any{"project": "p", "provider": "synthetic", "source_instance": "fixture", "messages": []map[string]any{{"session_id": "good", "message_id": "first", "text": "visible"}, {"session_id": "deleted", "message_id": "denied", "text": "must not enter WAL"}, {"session_id": "good", "message_id": "third", "text": "unattempted"}}}
			code, b := do(t, "POST", f.ts.URL+"/v1/capture", f.writer, body)
			if code != 409 || b["accepted"] != float64(1) {
				t.Fatal("wrong accepted prefix", code, b)
			}
			receipts, ok := b["receipts"].([]any)
			if !ok || len(receipts) != 1 || receipts[0] != `["p","fixture","good","first"]` {
				t.Fatal("wrong prefix receipt", b)
			}
			p, e := f.ing.Progress()
			if e != nil || p.Accepted != 1 {
				t.Fatal("denied/unattempted payload entered intake", p, e)
			}
			if _, e = f.ing.Drain(); e != nil {
				t.Fatal(e)
			} // only the single accepted visible record exists
			code, g := do(t, "POST", f.ts.URL+"/v1/grants", opHdr(), map[string]any{"principal_id": "reader", "kind": "agent", "projects": []string{"p"}, "ops": []string{"archive.query"}, "secret": "fixture-reader"})
			if code != 201 {
				t.Fatal(code, g)
			}
			h := map[string]string{"X-Principal-Id": "reader", "X-Grant-Epoch": itoa(int64(g["epoch"].(float64))), "X-Secret": "fixture-reader"}
			code, b = do(t, "GET", f.ts.URL+"/v1/archive/query?project=p", h, nil)
			if code != 200 || len(b["hits"].([]any)) != 1 {
				t.Fatal("prefix unreadable", code, b)
			}
			hit := b["hits"].([]any)[0].(map[string]any)
			if hit["MessageID"] != "first" || hit["Text"] != "visible" {
				t.Fatal("wrong retained prefix", hit)
			}
		})
	}
}
