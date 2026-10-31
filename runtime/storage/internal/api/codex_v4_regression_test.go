package api_test

// Codex v4 regression. The reproduced P1: a durable-accept whose committed-index persist fails
// returns an error to the caller (503), yet the record is DURABLY accepted (frame+accept marker
// fsync'd, WAL dedup set) and will replay and drain to the archive. A second request that sampled
// the ingestor's accepted-bytes total BEFORE this one must still see that durable growth, or it
// recomputes delta=0 and re-spends the same live/free budget -> two durable records admitted
// against a one-record budget. This probe (adopted faithfully from the v4 review, reformatted and
// extended with a retry/no-double-charge assertion) drives it over real HTTP with a deterministic
// meter barrier, for BOTH the live-cap and the free-headroom dimension.

import (
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"sync/atomic"
	"testing"

	"aifactory.local/storage/internal/api"
	"aifactory.local/storage/internal/archive"
	"aifactory.local/storage/internal/config"
	"aifactory.local/storage/internal/control"
	"aifactory.local/storage/internal/ingest"
	"aifactory.local/storage/internal/registry"
)

func TestCodexV4ErrorAcceptReservesStaleBudget(t *testing.T) {
	for _, dimension := range []string{"live", "headroom"} {
		t.Run(dimension, func(t *testing.T) {
			d := t.TempDir()
			ctl, e := control.Initialize(filepath.Join(d, "ctl"))
			if e != nil {
				t.Fatal(e)
			}
			defer ctl.Close()
			op := registry.Principal{Kind: registry.Operator}
			ctl.MintProject(op, "p", "p")
			ctl.SetConsent(op, "p", "synthetic", "capture", true)

			r := archive.Record{Project: "p", Provider: "synthetic", SourceInstance: "i", SessionID: "s", MessageID: "a", Type: archive.TypeMessage, Text: "x", ConsentEpoch: 1}
			cost := ingest.RecordCost(r)

			// Budget sized for EXACTLY one record, in whichever dimension this subcase exercises.
			cfg := config.Default()
			cfg.CaptureEnabled = true
			u := config.Usage{FreeBytes: 1 << 40}
			if dimension == "live" {
				cfg.LiveCapBytes = cost
			} else {
				u.FreeBytes = cfg.FreeHeadroom + cost
			}

			store := archive.NewMemStore()
			wd := filepath.Join(d, "ing")
			ing, e := ingest.Open(wd, config.NewAccountant(cfg), store)
			if e != nil {
				t.Fatal(e)
			}
			defer ing.Close()

			srv := api.New(ctl, cfg, "op", opSecret)
			srv.SetIngestor(ing)

			// Deterministic concurrency barrier: the FIRST request into the meter (request "b")
			// blocks until released; it has already sampled its accepted-bytes baseline. The
			// SECOND meter call (request "a") returns immediately so A can run to its durable
			// error while B is parked.
			var measured atomic.Int32
			entered, release := make(chan struct{}), make(chan struct{})
			srv.SetUsageMeter(func() (config.Usage, error) {
				if measured.Add(1) == 1 {
					close(entered)
					<-release
				}
				return u, nil
			})

			ts := httptest.NewServer(srv.Handler())
			defer ts.Close()
			request := func(id string) (int, map[string]any) {
				fx := v2Fixture("x")
				fx["messages"] = []map[string]any{{"session_id": "s", "message_id": id, "text": "x"}}
				return do(t, http.MethodPost, ts.URL+"/v1/capture", opHdr(), fx)
			}

			done := make(chan int, 1)
			go func() { code, _ := request("b"); done <- code }()
			<-entered // B has sampled its baseline and is parked inside the meter.

			// Inject the committed-index fault so A's durable accept fails AFTER the frame+accept
			// marker are fsync'd (a directory cannot be appended to as the index file).
			idx := filepath.Join(wd, "committed.idx")
			os.Remove(idx)
			os.Mkdir(idx, 0700)
			first, body := request("a")
			if first != 503 {
				close(release)
				<-done
				t.Fatalf("expected accepted-error 503 got %d %v", first, body)
			}

			// Clear the fault and release B. B must now observe A's durable growth and be rejected.
			os.Remove(idx)
			os.WriteFile(idx, nil, 0600)
			close(release)
			second := <-done

			n, e := ing.AcceptedCount()
			if e != nil {
				t.Fatal(e)
			}
			if n > 1 {
				t.Fatalf("%s: stale request admitted after durable-error: firstHTTP=%d secondHTTP=%d accepted=%d acceptedTotal=%d cost=%d", dimension, first, second, n, ing.AcceptedBytes(), cost)
			}
			if second != 503 {
				t.Fatalf("%s: parked request must be rejected once A's durable byte-growth is visible, got HTTP=%d", dimension, second)
			}
			if got := ing.AcceptedBytes(); got != cost {
				t.Fatalf("%s: durable-error accept must reserve exactly one record's cost: acceptedTotal=%d want=%d", dimension, got, cost)
			}

			// Retry of A's record (same identity, same payload) must be a benign no-op: it is
			// recognized as a durable duplicate and does NOT charge the budget a second time.
			retry, rbody := request("a")
			if retry != 200 {
				t.Fatalf("%s: retry of a durably-accepted record must succeed as a duplicate no-op, got HTTP=%d %v", dimension, retry, rbody)
			}
			if got := ing.AcceptedBytes(); got != cost {
				t.Fatalf("%s: retry double-charged the budget: acceptedTotal=%d want=%d", dimension, got, cost)
			}
			if n2, _ := ing.AcceptedCount(); n2 != 1 {
				t.Fatalf("%s: retry appended a second frame: accepted=%d want=1", dimension, n2)
			}
		})
	}
}
