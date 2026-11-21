//go:build integration

// End-to-end integration test through the REAL API handlers and the capture adapter against
// a REAL MongoDB archive (MONGO_URI; skipped otherwise). It drives the full path:
// operator setup -> POST /v1/capture (synthetic fixture) -> ingestion -> durable archive ->
// GET /v1/archive/query, and the consent / redaction / revocation / deletion-barrier /
// cross-project gates. It is NOT a per-package unit test: the data flows through HTTP.
package api_test

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"aifactory.local/storage/internal/api"
	"aifactory.local/storage/internal/archive"
	"aifactory.local/storage/internal/config"
	"aifactory.local/storage/internal/control"
	"aifactory.local/storage/internal/ingest"
	"aifactory.local/storage/internal/meter"
)

const e2eOpSecret = "e2e-operator-secret"

func e2eServer(t *testing.T) (*httptest.Server, *archive.MongoStore) {
	return e2eServerWith(t, nil)
}

// e2eServerWith builds the real API server over a real Mongo archive, applying an optional
// config tweak (e.g. tiny caps) before Validate.
func e2eServerWith(t *testing.T, tweak func(*config.Config)) (*httptest.Server, *archive.MongoStore) {
	t.Helper()
	uri := os.Getenv("MONGO_URI")
	if uri == "" {
		t.Skip("MONGO_URI not set; skipping end-to-end integration test")
	}
	dir := t.TempDir()
	ctl, err := control.Initialize(filepath.Join(dir, "state"))
	if err != nil {
		t.Fatalf("control.Initialize: %v", err)
	}
	t.Cleanup(func() { ctl.Close() })

	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	db := fmt.Sprintf("e2e_%d", time.Now().UnixNano())
	store, err := archive.OpenMongo(ctx, uri, db, "archive")
	if err != nil {
		t.Fatalf("OpenMongo: %v", err)
	}
	// The isolated Mongo test container is ephemeral and torn down after the run, and each
	// test uses a unique database name, so closing the client is sufficient cleanup.
	t.Cleanup(func() { _ = store.Close() })

	cfg := config.Default()
	cfg.MongoEnabled = true
	cfg.CaptureEnabled = true
	cfg.MongoURI, cfg.MongoDB, cfg.MongoCollection = uri, db, "archive"
	if tweak != nil {
		tweak(&cfg)
	}
	if err := cfg.Validate(); err != nil {
		t.Fatalf("config.Validate: %v", err)
	}

	ing, err := ingest.Open(filepath.Join(dir, "ingest", "wal"), config.NewAccountant(cfg), store)
	if err != nil {
		t.Fatalf("ingest.Open: %v", err)
	}
	t.Cleanup(func() { ing.Close() })

	srv := api.New(ctl, cfg, "operator", e2eOpSecret)
	srv.SetAvailability(store.Available, nil)
	srv.SetIngestor(ing)
	srv.SetUsageMeter(func() (config.Usage, error) {
		sctx, scancel := context.WithTimeout(context.Background(), 3*time.Second)
		defer scancel()
		sz, err := store.StorageBytes(sctx)
		if err != nil {
			return config.Usage{}, err
		}
		return meter.Measure(filepath.Join(dir, "state"), filepath.Join(dir, "ingest", "wal"), sz)
	})
	ts := httptest.NewServer(srv.Handler())
	t.Cleanup(ts.Close)
	return ts, store
}

func op(t *testing.T, ts *httptest.Server, path string, body any) (int, map[string]any) {
	t.Helper()
	b, _ := json.Marshal(body)
	req, _ := http.NewRequest(http.MethodPost, ts.URL+path, bytes.NewReader(b))
	req.Header.Set("X-Operator-Secret", e2eOpSecret)
	return doReq(t, req)
}

func agentGet(t *testing.T, ts *httptest.Server, path, principal, epoch, secret string) (int, map[string]any) {
	t.Helper()
	req, _ := http.NewRequest(http.MethodGet, ts.URL+path, nil)
	req.Header.Set("X-Principal-Id", principal)
	req.Header.Set("X-Grant-Epoch", epoch)
	req.Header.Set("X-Secret", secret)
	return doReq(t, req)
}

func doReq(t *testing.T, req *http.Request) (int, map[string]any) {
	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		t.Fatal(err)
	}
	defer resp.Body.Close()
	var m map[string]any
	body, _ := io.ReadAll(resp.Body)
	_ = json.Unmarshal(body, &m)
	return resp.StatusCode, m
}

func fixture(project string) map[string]any {
	return map[string]any{
		"provider": "synthetic", "source_instance": "inst-1", "project": project,
		"messages": []map[string]any{
			{"session_id": "s1", "message_id": "m1", "seq": 1, "role": "user", "text": "hello archive", "kind": "message",
				"hidden_reasoning": "SECRET CHAIN OF THOUGHT", "secrets": map[string]string{"api_key": "sk-should-never-persist"}},
			{"session_id": "s1", "message_id": "m2", "seq": 2, "role": "assistant", "text": "a summary", "kind": "summary"},
		},
	}
}

func TestE2ECaptureThroughAPIToArchiveAndQuery(t *testing.T) {
	ts, store := e2eServer(t)

	// Operator setup, all via HTTP.
	if code, _ := op(t, ts, "/v1/projects", map[string]string{"UUID": "proj-A", "Label": "A"}); code != 201 {
		t.Fatalf("mint proj-A: %d", code)
	}
	if code, _ := op(t, ts, "/v1/consent", map[string]any{"Project": "proj-A", "Provider": "synthetic", "Capability": "capture", "Enabled": true}); code != 200 {
		t.Fatalf("enable consent: %d", code)
	}
	code, gm := op(t, ts, "/v1/grants", map[string]any{"principal_id": "agent-1", "kind": "agent", "projects": []string{"proj-A"}, "ops": []string{"archive.query"}, "secret": "sek"})
	if code != 201 {
		t.Fatalf("grant: %d", code)
	}
	epoch := fmt.Sprintf("%v", int64(gm["epoch"].(float64)))

	// Capture a synthetic fixture (prohibited fields present in the input).
	code, cm := op(t, ts, "/v1/capture", fixture("proj-A"))
	if code != 200 {
		t.Fatalf("capture: %d (%v)", code, cm)
	}
	if acc := cm["accepted"].(float64); acc != 2 {
		t.Fatalf("expected 2 accepted, got %v", acc)
	}
	if red, _ := cm["redactions"].([]any); len(red) != 2 {
		t.Fatalf("expected 2 redactions (hidden_reasoning + secrets), got %v", cm["redactions"])
	}

	// Query back through the API as the authorized agent.
	code, qm := agentGet(t, ts, "/v1/archive/query?project=proj-A&q=hello", "agent-1", epoch, "sek")
	if code != 200 {
		t.Fatalf("query: %d", code)
	}
	hits, _ := qm["hits"].([]any)
	if len(hits) != 1 {
		t.Fatalf("expected 1 message hit for 'hello', got %d", len(hits))
	}
	// Redaction end-to-end: the stored/served record must carry no prohibited data.
	raw, _ := json.Marshal(qm)
	if bytes.Contains(raw, []byte("CHAIN OF THOUGHT")) || bytes.Contains(raw, []byte("sk-should-never-persist")) {
		t.Fatalf("prohibited content leaked into the archive/query result: %s", raw)
	}

	// Cross-project denial: agent-1 is granted proj-A only.
	if code, _ := op(t, ts, "/v1/projects", map[string]string{"UUID": "proj-B", "Label": "B"}); code != 201 {
		t.Fatalf("mint proj-B: %d", code)
	}
	if code, _ := agentGet(t, ts, "/v1/archive/query?project=proj-B&q=", "agent-1", epoch, "sek"); code != http.StatusForbidden {
		t.Fatalf("cross-project query must be 403, got %d", code)
	}

	// Consent revocation: after revoke, the previously-captured record is withheld on serve.
	if code, _ := op(t, ts, "/v1/consent", map[string]any{"Project": "proj-A", "Provider": "synthetic", "Capability": "capture", "Enabled": false}); code != 200 {
		t.Fatalf("revoke consent: %d", code)
	}
	code, qm2 := agentGet(t, ts, "/v1/archive/query?project=proj-A&q=hello", "agent-1", epoch, "sek")
	if code != 200 {
		t.Fatalf("query after revoke: %d", code)
	}
	if h, _ := qm2["hits"].([]any); len(h) != 0 {
		t.Fatalf("after consent revocation the serve-gate must withhold the record, got %d hits", len(h))
	}

	_ = store
}

// End-to-end through the API using the PROVIDER-SPECIFIC Claude Code JSONL parser (not just
// its unit tests): POST raw synthetic JSONL -> parse -> ingestion -> real Mongo -> query.
// Thinking/tool internals must be absent end-to-end. Real-source fidelity remains NOT_TESTED.
func TestE2EClaudeCodeJSONLThroughAPI(t *testing.T) {
	ts, store := e2eServer(t)
	if code, _ := op(t, ts, "/v1/projects", map[string]string{"UUID": "proj-A", "Label": "A"}); code != 201 {
		t.Fatalf("mint: %d", code)
	}
	// Consent is per (project, provider); the provider for this endpoint is "claude-code".
	if code, _ := op(t, ts, "/v1/consent", map[string]any{"Project": "proj-A", "Provider": "claude-code", "Capability": "capture", "Enabled": true}); code != 200 {
		t.Fatalf("consent: %d", code)
	}
	code, gm := op(t, ts, "/v1/grants", map[string]any{"principal_id": "agent-1", "kind": "agent", "projects": []string{"proj-A"}, "ops": []string{"archive.query"}, "secret": "sek"})
	if code != 201 {
		t.Fatalf("grant: %d", code)
	}
	epoch := fmt.Sprintf("%v", int64(gm["epoch"].(float64)))

	jsonl := strings.Join([]string{
		`{"type":"user","uuid":"u1","parentUuid":"","sessionId":"sess","message":{"role":"user","content":[{"type":"text","text":"please refactor the parser"}]}}`,
		`{"type":"assistant","uuid":"a1","parentUuid":"u1","sessionId":"sess","message":{"role":"assistant","content":[{"type":"thinking","text":"SECRET-COT-leak"},{"type":"tool_use","text":"{\"cmd\":\"rm\"}"},{"type":"text","text":"refactor complete"}]}}`,
	}, "\n")

	// POST raw JSONL to the provider-specific endpoint.
	req, _ := http.NewRequest(http.MethodPost, ts.URL+"/v1/capture/claude-code?project=proj-A&source_instance=inst-1", bytes.NewReader([]byte(jsonl)))
	req.Header.Set("X-Operator-Secret", e2eOpSecret)
	code, cm := doReq(t, req)
	if code != 200 {
		t.Fatalf("claude-code capture: %d (%v)", code, cm)
	}
	if acc := cm["accepted"].(float64); acc != 2 {
		t.Fatalf("expected 2 message records (user + assistant text), got %v", acc)
	}

	// Query back as the authorized agent; thinking/tool internals must be absent end-to-end.
	code, qm := agentGet(t, ts, "/v1/archive/query?project=proj-A&q=refactor", "agent-1", epoch, "sek")
	if code != 200 {
		t.Fatalf("query: %d", code)
	}
	if h, _ := qm["hits"].([]any); len(h) != 2 {
		t.Fatalf("expected 2 hits for 'refactor', got %d", len(h))
	}
	raw, _ := json.Marshal(qm)
	if bytes.Contains(raw, []byte("SECRET-COT-leak")) || bytes.Contains(raw, []byte(`"cmd"`)) {
		t.Fatalf("thinking/tool internals leaked end-to-end: %s", raw)
	}
	// Direct archive read (Mongo): prohibited content must be absent there too.
	for _, r := range mustFetch(t, store, "proj-A") {
		blob, _ := json.Marshal(r)
		if bytes.Contains(blob, []byte("SECRET-COT-leak")) || bytes.Contains(blob, []byte(`"cmd"`)) {
			t.Fatalf("prohibited content reached the archive")
		}
	}
}

// Physical purge through the API: capture -> barrier (hides) -> purge (physically erases
// from Mongo). Purge is refused without a deletion barrier.
func TestE2EPurgePhysicallyErases(t *testing.T) {
	ts, store := e2eServer(t)
	if code, _ := op(t, ts, "/v1/projects", map[string]string{"UUID": "proj-A", "Label": "A"}); code != 201 {
		t.Fatal(code)
	}
	if code, _ := op(t, ts, "/v1/consent", map[string]any{"Project": "proj-A", "Provider": "synthetic", "Capability": "capture", "Enabled": true}); code != 200 {
		t.Fatal(code)
	}
	// An agent grant so we can also prove erasure via the authenticated READ path (not only
	// the operator-internal store view).
	code0, gm := op(t, ts, "/v1/grants", map[string]any{"principal_id": "agent-1", "kind": "agent", "projects": []string{"proj-A"}, "ops": []string{"archive.query"}, "secret": "sek"})
	if code0 != 201 {
		t.Fatalf("grant: %d", code0)
	}
	epoch := fmt.Sprintf("%v", int64(gm["epoch"].(float64)))

	if code, m := op(t, ts, "/v1/capture", fixture("proj-A")); code != 200 {
		t.Fatalf("capture: %d (%v)", code, m)
	}
	if n := len(mustFetch(t, store, "proj-A")); n != 2 {
		t.Fatalf("expected 2 committed records, got %d", n)
	}
	// Purge without a deletion barrier must be refused.
	if code, _ := op(t, ts, "/v1/purge/project", map[string]string{"Project": "proj-A"}); code != http.StatusConflict {
		t.Fatalf("purge without a barrier must be 409, got %d", code)
	}
	// Set the barrier, then purge.
	if code, _ := op(t, ts, "/v1/barriers/project", map[string]string{"Project": "proj-A"}); code != 200 {
		t.Fatal(code)
	}
	code, pm := op(t, ts, "/v1/purge/project", map[string]string{"Project": "proj-A"})
	if code != 200 {
		t.Fatalf("purge: %d (%v)", code, pm)
	}
	if p, _ := pm["archive_purged"].(float64); p != 2 {
		t.Fatalf("expected 2 archive records purged, got %v", pm["archive_purged"])
	}
	if complete, _ := pm["complete"].(bool); !complete {
		t.Fatalf("purge of fully-parseable records must report complete=true, got %v", pm)
	}
	// Physical erasure is proved along THREE independent axes, not just serve-gate hiding:
	//
	// (a) Absent payload in the live stores. Archive: Mongo holds zero records for the project.
	if n := len(mustFetch(t, store, "proj-A")); n != 0 {
		t.Fatalf("records must be PHYSICALLY erased from Mongo after purge, got %d", n)
	}
	//     WAL: the purge response reports the intake-journal frames were physically dropped too
	//     (Compact), so a later re-drain cannot re-materialize the payload.
	if wd, _ := pm["wal_dropped"].(float64); wd != 2 {
		t.Fatalf("expected 2 WAL frames physically dropped, got %v", pm["wal_dropped"])
	}
	// (b) Unavailable through the API: the authorized agent read-back returns no hits.
	code, qm := agentGet(t, ts, "/v1/archive/query?project=proj-A&q=hello", "agent-1", epoch, "sek")
	if code != 200 {
		t.Fatalf("post-purge query status: %d", code)
	}
	if hits, _ := qm["hits"].([]any); len(hits) != 0 {
		t.Fatalf("API must return no hits after physical erasure, got %v", qm["hits"])
	}
	// (c) Republish prohibited: re-capturing the same project is refused by the retained
	// barrier (409), so erased content cannot be re-admitted.
	if code, _ := op(t, ts, "/v1/capture", fixture("proj-A")); code != http.StatusConflict {
		t.Fatalf("re-capture after a deletion barrier must be refused (409), got %d", code)
	}
	if n := len(mustFetch(t, store, "proj-A")); n != 0 {
		t.Fatalf("refused re-capture must not resurrect any record, got %d", n)
	}
}

func TestE2ECaptureRequiresConsentAndBarrierBlocks(t *testing.T) {
	ts, _ := e2eServer(t)
	if code, _ := op(t, ts, "/v1/projects", map[string]string{"UUID": "proj-C", "Label": "C"}); code != 201 {
		t.Fatal(code)
	}
	// Capture without consent -> 403.
	if code, _ := op(t, ts, "/v1/capture", fixture("proj-C")); code != http.StatusForbidden {
		t.Fatalf("capture without consent must be 403, got %d", code)
	}
	// Enable consent, then a project deletion barrier -> capture refused (409).
	if code, _ := op(t, ts, "/v1/consent", map[string]any{"Project": "proj-C", "Provider": "synthetic", "Capability": "capture", "Enabled": true}); code != 200 {
		t.Fatal(code)
	}
	if code, _ := op(t, ts, "/v1/barriers/project", map[string]string{"Project": "proj-C"}); code != 200 {
		t.Fatal(code)
	}
	if code, _ := op(t, ts, "/v1/capture", fixture("proj-C")); code != http.StatusConflict {
		t.Fatalf("capture under a deletion barrier must be 409, got %d", code)
	}
}

func mustFetch(t *testing.T, s archive.Store, project string) []archive.Record {
	t.Helper()
	r, err := s.Fetch(project)
	if err != nil {
		t.Fatalf("Fetch(%q): %v", project, err)
	}
	return r
}

func TestE2EArchiveMessageRetrieval(t *testing.T) {
	ts, _ := e2eServer(t)
	if code, _ := op(t, ts, "/v1/projects", map[string]string{"UUID": "fetch-project", "Label": "fetch"}); code != 201 {
		t.Fatal(code)
	}
	if code, _ := op(t, ts, "/v1/consent", map[string]any{"Project": "fetch-project", "Provider": "synthetic", "Capability": "capture", "Enabled": true}); code != 200 {
		t.Fatal(code)
	}
	code, g := op(t, ts, "/v1/grants", map[string]any{"principal_id": "fetch-agent", "kind": "agent", "projects": []string{"fetch-project"}, "ops": []string{"archive.query"}, "secret": "synthetic-fetch"})
	if code != 201 {
		t.Fatal(code)
	}
	epoch := fmt.Sprint(int64(g["epoch"].(float64)))
	if code, b := op(t, ts, "/v1/capture", fixture("fetch-project")); code != 200 || b["committed"] != float64(2) {
		t.Fatal(code, b)
	}
	for _, tc := range []struct{ id, text, kind string }{{"m1", "hello archive", "message"}, {"m2", "a summary", "summary"}} {
		path := "/v1/archive/message?project=fetch-project&source_instance=inst-1&session_id=s1&message_id=" + tc.id
		code, b := agentGet(t, ts, path, "fetch-agent", epoch, "synthetic-fetch")
		if code != 200 {
			t.Fatal(code, b)
		}
		rec := b["record"].(map[string]any)
		if rec["Text"] != tc.text || rec["Type"] != tc.kind || rec["MessageID"] != tc.id || rec["SourceInstance"] != "inst-1" {
			t.Fatal(rec)
		}
		code, _ = agentGet(t, ts, strings.Replace(path, "inst-1", "other-source", 1), "fetch-agent", epoch, "synthetic-fetch")
		if code != 404 {
			t.Fatalf("foreign source: %d", code)
		}
	}
	if code, _ := op(t, ts, "/v1/consent", map[string]any{"Project": "fetch-project", "Provider": "synthetic", "Capability": "capture", "Enabled": false}); code != 200 {
		t.Fatal(code)
	}
	if code, _ := agentGet(t, ts, "/v1/archive/message?project=fetch-project&source_instance=inst-1&session_id=s1&message_id=m1", "fetch-agent", epoch, "synthetic-fetch"); code != 404 {
		t.Fatalf("revoked capture: %d", code)
	}
}

func TestE2EArchiveContext(t *testing.T) {
	ts, _ := e2eServer(t)
	if code, _ := op(t, ts, "/v1/projects", map[string]string{"UUID": "context-project", "Label": "context"}); code != 201 {
		t.Fatal(code)
	}
	if code, _ := op(t, ts, "/v1/consent", map[string]any{"Project": "context-project", "Provider": "synthetic", "Capability": "capture", "Enabled": true}); code != 200 {
		t.Fatal(code)
	}
	code, g := op(t, ts, "/v1/grants", map[string]any{"principal_id": "context-agent", "kind": "agent", "projects": []string{"context-project"}, "ops": []string{"archive.query"}, "secret": "synthetic-context"})
	if code != 201 {
		t.Fatal(code)
	}
	epoch := fmt.Sprint(int64(g["epoch"].(float64)))
	f := fixture("context-project")
	f["messages"].([]map[string]any)[1]["parent_id"] = "m1"
	if code, b := op(t, ts, "/v1/capture", f); code != 200 {
		t.Fatal(code, b)
	}
	code, b := agentGet(t, ts, "/v1/archive/context?project=context-project&source_instance=inst-1&session_id=s1&message_id=m2", "context-agent", epoch, "synthetic-context")
	if code != 200 {
		t.Fatal(code, b)
	}
	rows := b["records"].([]any)
	if len(rows) != 2 || rows[0].(map[string]any)["MessageID"] != "m2" || rows[1].(map[string]any)["MessageID"] != "m1" || b["stop_reason"] != "no_parent" {
		t.Fatal(b)
	}
}
