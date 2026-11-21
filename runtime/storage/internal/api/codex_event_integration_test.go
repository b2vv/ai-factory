//go:build integration

package api_test

import (
	"aifactory.local/storage/internal/api"
	"aifactory.local/storage/internal/archive"
	"aifactory.local/storage/internal/capture"
	"aifactory.local/storage/internal/config"
	"aifactory.local/storage/internal/control"
	"aifactory.local/storage/internal/ingest"
	"aifactory.local/storage/internal/search"
	"context"
	"fmt"
	"net/http/httptest"
	"net/url"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

// Synthetic documented events over real databases, never a real-history claim.
func TestCodexEventDecisionSearchDuplicateAndRestart(t *testing.T) { testCodexReplay(t, false) }
func TestCodexV2SnapshotsSearchDuplicateAndRestart(t *testing.T)   { testCodexReplay(t, true) }
func testCodexReplay(t *testing.T, snapshots bool) {
	uri, dsn := os.Getenv("MONGO_URI"), os.Getenv("PG_DSN")
	if uri == "" || dsn == "" {
		t.Skip("synthetic Mongo/PG endpoints required")
	}
	root := t.TempDir()
	cp, ip := filepath.Join(root, "control"), filepath.Join(root, "ingest")
	c, e := control.Initialize(cp)
	if e != nil {
		t.Fatal(e)
	}
	c.Close()
	project := fmt.Sprintf("codex_events_%d", time.Now().UnixNano())
	cfg := config.Default()
	cfg.CaptureEnabled = true
	var ts *httptest.Server
	var server *api.Server
	var ctl *control.Durable
	var ing *ingest.Ingestor
	var store *archive.MongoStore
	var idx *search.Store
	open := func() {
		var err error
		ctx, cancel := context.WithTimeout(context.Background(), 15*time.Second)
		defer cancel()
		ctl, err = control.Open(cp)
		if err != nil {
			t.Fatal(err)
		}
		store, err = archive.OpenMongo(ctx, uri, project, "archive")
		if err != nil {
			t.Fatal(err)
		}
		idx, err = search.Open(ctx, dsn)
		if err != nil {
			t.Fatal(err)
		}
		ing, err = ingest.Open(ip, config.NewAccountant(cfg), store)
		if err != nil {
			t.Fatal(err)
		}
		server = api.New(ctl, cfg, "op", opSecret)
		server.SetIngestor(ing)
		server.SetSearchStore(idx)
		server.SetAvailability(store.Available, nil)
		server.SetUsageMeter(func() (config.Usage, error) { return config.Usage{FreeBytes: 1 << 40}, nil })
		ts = httptest.NewServer(server.Handler())
	}
	closeAll := func() { ts.Close(); ing.Close(); ctl.Close(); idx.Close(); store.Close() }
	open()
	defer func() { closeAll() }()
	if code, _ := do(t, "POST", ts.URL+"/v1/projects", opHdr(), map[string]string{"UUID": project, "Label": "synthetic"}); code != 201 {
		t.Fatal(code)
	}
	provider, path, wantRecords, wantHits := capture.CodexEventProvider, "/v1/capture/codex-event", 2, 1
	if snapshots {
		provider, path, wantRecords, wantHits = capture.CodexSnapshotProvider, "/v1/capture/codex-event-v2", 104, 103
	}
	if code, _ := do(t, "POST", ts.URL+"/v1/consent", opHdr(), map[string]any{"Project": project, "Provider": provider, "Capability": "capture", "Enabled": true}); code != 200 {
		t.Fatal(code)
	}
	_, g := do(t, "POST", ts.URL+"/v1/grants", opHdr(), map[string]any{"principal_id": "reader", "kind": "agent", "projects": []string{project}, "ops": []string{"archive.query", "search"}, "secret": "synthetic-reader"})
	epoch := itoa(int64(g["epoch"].(float64)))
	events := []map[string]any{{"hook_event_name": "UserPromptSubmit", "session_id": "session_sample", "turn_id": "turn_sample", "prompt": "Which retention policy?"}, {"hook_event_name": "Stop", "session_id": "session_sample", "turn_id": "turn_sample", "last_assistant_message": "Decision: preserve originalsource and never evict accepted data."}}
	if snapshots {
		for _, ev := range events {
			ev["schema_version"] = 2
		}
		events[1]["stop_hook_active"] = false
		events = append(events, map[string]any{"schema_version": 2, "hook_event_name": "Stop", "session_id": "session_sample", "turn_id": "turn_sample", "last_assistant_message": "Continued originalsource decision: preserve the final snapshot too.", "stop_hook_active": true})
	}
	if snapshots {
		for n := 0; n < 101; n++ {
			events = append(events, map[string]any{"schema_version": 2, "hook_event_name": "Stop", "session_id": "session_sample", "turn_id": "turn_sample", "last_assistant_message": fmt.Sprintf("originalsource snapshot %d", n), "stop_hook_active": true})
		}
	}
	post := func() {
		for _, v := range events {
			code, _ := do(t, "POST", ts.URL+path+"?project="+project+"&source_instance=fixture_export", opHdr(), v)
			if code != 200 {
				t.Fatal("capture", code)
			}
		}
	}
	query := func() {
		seen := map[string]bool{}
		cursor := ""
		for page := 0; page < 10; page++ {
			code, b := agentQuery(t, ts.URL, "/v1/search/query?project="+project+"&q=originalsource&cursor="+url.QueryEscape(cursor), "reader", epoch, "synthetic-reader")
			if code != 200 {
				t.Fatal(code, b)
			}
			hits := b["hits"].([]any)
			if len(hits) > 100 {
				t.Fatal("page exceeds limit")
			}
			for _, item := range hits {
				h := item.(map[string]any)
				id := h["MessageID"].(string)
				if seen[id] {
					t.Fatal("duplicate across pages")
				}
				seen[id] = true
				if h["SessionID"] != "session_sample" || h["SourceInstance"] != "fixture_export" || h["Provider"] != provider {
					t.Fatal("source identity missing", h)
				}
				if snapshots {
					if !strings.HasPrefix(id, "v2/turn_sample/assistant/") {
						t.Fatal("wrong snapshot ID", id)
					}
				} else if id != "turn_sample/assistant" {
					t.Fatal("legacy ID changed", id)
				}
			}
			cursor, _ = b["next_cursor"].(string)
			if cursor == "" {
				if snapshots && page == 0 {
					t.Fatal("large snapshot set did not paginate")
				}
				break
			}
			if page == 9 {
				t.Fatal("cursor failed to terminate")
			}
		}
		if len(seen) != wantHits {
			t.Fatalf("retrieved %d snapshots, want %d", len(seen), wantHits)
		}
	}

	post()
	// IndexOnce intentionally processes at most sixteen legacy source records.
	// Advance the actual bounded indexer until this fixture's complete set is covered.
	for indexed := 0; indexed < wantRecords; {
		n, err := server.IndexOnce()
		if err != nil || n <= 0 {
			t.Fatal("index made no progress", n, err)
		}
		indexed += n
	}
	query()
	n := ing.AcceptedBytes()
	post()
	if ing.AcceptedBytes() != n {
		t.Fatal("duplicate appended")
	}
	records, e := store.Fetch(project)
	if e != nil || len(records) != wantRecords {
		t.Fatal("archive count", len(records), e)
	}
	closeAll()
	open()
	query()
	post()
	records, e = store.Fetch(project)
	if e != nil || len(records) != wantRecords {
		t.Fatal("restart duplicate", len(records), e)
	}
	t.Log("SYNTHETIC: decision/source identity, duplicate, reopened runtime query PASS")
}
