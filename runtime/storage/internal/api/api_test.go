package api_test

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"testing"

	"aifactory.local/storage/internal/api"
	"aifactory.local/storage/internal/config"
	"aifactory.local/storage/internal/control"
)

const opSecret = "op-secret"

// initDir runs the explicit first-time operator initialization for a pristine state dir
// and releases it, so a subsequent control.Open finds an initialized registry. Normal Open
// no longer auto-initializes (A).
func initDir(t *testing.T, dir string) {
	t.Helper()
	ctl, err := control.Initialize(dir)
	if err != nil {
		t.Fatalf("control.Initialize: %v", err)
	}
	ctl.Close()
}

func newServer(t *testing.T, dir string) *httptest.Server {
	t.Helper()
	ctl, err := control.Open(dir)
	if err != nil {
		t.Fatalf("control.Open: %v", err)
	}
	t.Cleanup(func() { ctl.Close() })
	srv := api.New(ctl, config.Default(), "operator", opSecret)
	ts := httptest.NewServer(srv.Handler())
	t.Cleanup(ts.Close)
	return ts
}

func do(t *testing.T, method, url string, hdr map[string]string, body any) (int, map[string]any) {
	t.Helper()
	var r io.Reader
	if body != nil {
		b, _ := json.Marshal(body)
		r = bytes.NewReader(b)
	}
	req, err := http.NewRequest(method, url, r)
	if err != nil {
		t.Fatal(err)
	}
	for k, v := range hdr {
		req.Header.Set(k, v)
	}
	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		t.Fatal(err)
	}
	defer resp.Body.Close()
	var m map[string]any
	_ = json.NewDecoder(resp.Body).Decode(&m)
	return resp.StatusCode, m
}

func opHdr() map[string]string { return map[string]string{"X-Operator-Secret": opSecret} }

func TestHealthOpen(t *testing.T) {
	dir := t.TempDir()
	initDir(t, dir)
	ts := newServer(t, dir)
	code, m := do(t, http.MethodGet, ts.URL+"/health", nil, nil)
	if code != 200 {
		t.Fatalf("health code %d", code)
	}
	if m["registry_blocked"] != false {
		t.Fatalf("fresh registry must not be blocked: %v", m["registry_blocked"])
	}
	if m["mode"] != "file-only" {
		t.Fatalf("expected file-only mode, got %v", m["mode"])
	}
}

func TestOperatorAuthRequiredForMutations(t *testing.T) {
	dir := t.TempDir()
	initDir(t, dir)
	ts := newServer(t, dir)
	code, _ := do(t, http.MethodPost, ts.URL+"/v1/projects", nil, map[string]string{"UUID": "p1"})
	if code != http.StatusUnauthorized {
		t.Fatalf("mutation without operator secret must be 401, got %d", code)
	}
	code, _ = do(t, http.MethodPost, ts.URL+"/v1/projects", opHdr(), map[string]string{"UUID": "p1", "Label": "l"})
	if code != http.StatusCreated {
		t.Fatalf("operator mint must be 201, got %d", code)
	}
}

func TestAgentAuthorizationAndCrossProjectDenial(t *testing.T) {
	dir := t.TempDir()
	initDir(t, dir)
	ts := newServer(t, dir)
	// operator sets up two projects + an agent grant on proj-A.
	for _, p := range []string{"proj-A", "proj-B"} {
		if code, _ := do(t, http.MethodPost, ts.URL+"/v1/projects", opHdr(), map[string]string{"UUID": p, "Label": "l"}); code != 201 {
			t.Fatalf("mint %s: %d", p, code)
		}
	}
	code, gm := do(t, http.MethodPost, ts.URL+"/v1/grants", opHdr(), map[string]any{
		"principal_id": "agent-1", "kind": "agent", "projects": []string{"proj-A"},
		"ops": []string{"archive.query"}, "secret": "sek",
	})
	if code != 201 {
		t.Fatalf("issue grant: %d", code)
	}
	epoch := fmt.Sprintf("%v", int64(gm["epoch"].(float64)))

	agent := map[string]string{"X-Principal-Id": "agent-1", "X-Grant-Epoch": epoch, "X-Secret": "sek"}

	// granted project+op
	if code, _ := do(t, http.MethodGet, ts.URL+"/v1/whoami?project=proj-A&op=archive.query", agent, nil); code != 200 {
		t.Fatalf("agent must be authorized on proj-A, got %d", code)
	}
	// cross-project denial (P10)
	if code, _ := do(t, http.MethodGet, ts.URL+"/v1/whoami?project=proj-B&op=archive.query", agent, nil); code != http.StatusForbidden {
		t.Fatalf("agent must be denied proj-B, got %d", code)
	}
	// bad secret
	bad := map[string]string{"X-Principal-Id": "agent-1", "X-Grant-Epoch": epoch, "X-Secret": "nope"}
	if code, _ := do(t, http.MethodGet, ts.URL+"/v1/whoami?project=proj-A&op=archive.query", bad, nil); code != http.StatusForbidden {
		t.Fatalf("bad secret must be denied, got %d", code)
	}
	// revoke -> denied
	if code, _ := do(t, http.MethodPost, ts.URL+"/v1/grants/revoke", opHdr(), map[string]string{"principal_id": "agent-1"}); code != 200 {
		t.Fatalf("revoke: %d", code)
	}
	if code, _ := do(t, http.MethodGet, ts.URL+"/v1/whoami?project=proj-A&op=archive.query", agent, nil); code != http.StatusForbidden {
		t.Fatalf("revoked agent must be denied, got %d", code)
	}
}

func TestBlockedRegistryReturns503AndHealthShowsBlocked(t *testing.T) {
	dir := t.TempDir()
	// Create then corrupt the durable log so a reopen is BLOCKED.
	ctl, err := control.Initialize(dir)
	if err != nil {
		t.Fatal(err)
	}
	// one mutation so there is an accepted frame to corrupt
	if code, _ := func() (int, map[string]any) {
		s := api.New(ctl, config.Default(), "operator", opSecret)
		ts := httptest.NewServer(s.Handler())
		defer ts.Close()
		return do(t, http.MethodPost, ts.URL+"/v1/projects", opHdr(), map[string]string{"UUID": "p1", "Label": "l"})
	}(); code != 201 {
		t.Fatalf("seed mint: %d", code)
	}
	ctl.Close()
	dataPath := filepath.Join(dir, "wal", "data")
	b, err := os.ReadFile(dataPath)
	if err != nil || len(b) < 6 {
		t.Fatalf("read wal data: %v len %d", err, len(b))
	}
	b[len(b)-5] ^= 0xFF
	if err := os.WriteFile(dataPath, b, 0o600); err != nil {
		t.Fatal(err)
	}

	ts := newServer(t, dir) // reopen blocked
	code, m := do(t, http.MethodGet, ts.URL+"/health", nil, nil)
	if code != 200 || m["registry_blocked"] != true {
		t.Fatalf("health must report registry_blocked=true, got code=%d m=%v", code, m)
	}
	code, _ = do(t, http.MethodPost, ts.URL+"/v1/projects", opHdr(), map[string]string{"UUID": "p2", "Label": "l"})
	if code != http.StatusServiceUnavailable {
		t.Fatalf("mutation on a blocked registry must be 503, got %d", code)
	}
}
