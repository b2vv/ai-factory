package api_test

import (
	"aifactory.local/storage/internal/archive"
	"aifactory.local/storage/internal/budget"
	"aifactory.local/storage/internal/config"
	"aifactory.local/storage/internal/control"
	"aifactory.local/storage/internal/ingest"
	"aifactory.local/storage/internal/registry"
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"path/filepath"
	"strings"
	"sync/atomic"
	"testing"
)

type captureFixture struct {
	ts     *httptest.Server
	ctl    *control.Durable
	ing    *ingest.Ingestor
	writer map[string]string
}

func scopedFixture(t *testing.T, metadata bool, meter func() (config.Usage, error), sources ...archive.Store) captureFixture {
	t.Helper()
	var source archive.Store = archive.NewMemStore()
	if len(sources) > 0 {
		source = sources[0]
	}
	ts, _, i, c := captureServer(t, source, meter)
	op := registry.Principal{Kind: registry.Operator}
	for _, p := range []string{"p", "q"} {
		if e := c.MintProject(op, p, "fixture"); e != nil {
			t.Fatal(e)
		}
		for _, provider := range []string{"synthetic", "claude-code", "codex-hook-v1", "codex-hook-v2"} {
			if _, e := c.SetConsent(op, p, provider, "capture", true); e != nil {
				t.Fatal(e)
			}
		}
	}
	code, g := do(t, "POST", ts.URL+"/v1/grants", opHdr(), map[string]any{"principal_id": "writer", "kind": "agent", "projects": []string{"p"}, "ops": []string{"capture"}, "secret": "fixture-write-only"})
	if code != 201 {
		t.Fatal(code, g)
	}
	if metadata {
		root := t.TempDir()
		l, e := budget.Initialize(filepath.Join(root, "budget.bin"), budget.Policy{LiveCap: 1 << 30}, func() (budget.Sample, error) { return budget.LocalSample(root, 1<<30) })
		if e != nil {
			t.Fatal(e)
		}
		if e = c.AttachBudget(l); e != nil {
			t.Fatal(e)
		}
		if e = i.SetBudget(l); e != nil {
			t.Fatal(e)
		}
		for _, p := range []string{"p", "q"} {
			if e = c.BeginArchiveMigration(op, p, "generation-"+p); e != nil {
				t.Fatal(e)
			}
			if e = c.WithArchiveTransaction(op, p, func(tx *control.ArchiveTransaction) error {
				return tx.FinishMigration(func(control.ArchiveState) error { return nil })
			}); e != nil {
				t.Fatal(e)
			}
		}
	}
	return captureFixture{ts, c, i, map[string]string{"X-Principal-Id": "writer", "X-Grant-Epoch": itoa(int64(g["epoch"].(float64))), "X-Secret": "fixture-write-only"}}
}
func scopedRequest(t *testing.T, f captureFixture, route, project string, h map[string]string) (int, map[string]any) {
	t.Helper()
	path := "/v1/capture"
	body := `{"project":"` + project + `","provider":"synthetic","source_instance":"fixture","messages":[{"session_id":"s","message_id":"m","text":"visible"}]}`
	if route == "claude" {
		path += "/claude-code?project=" + project + "&source_instance=fixture"
		body = `{"type":"user","uuid":"m","sessionId":"s","message":{"role":"user","content":[{"type":"text","text":"visible"}]}}`
	}
	if route == "codex" {
		path += "/codex-event?project=" + project + "&source_instance=fixture"
		body = `{"hook_event_name":"UserPromptSubmit","session_id":"s","turn_id":"turn","prompt":"visible"}`
	}
	if route == "codex-v2" {
		path += "/codex-event-v2?project=" + project + "&source_instance=fixture"
		body = `{"schema_version":2,"hook_event_name":"UserPromptSubmit","session_id":"s","turn_id":"turn","prompt":"visible"}`
	}
	req, e := http.NewRequest("POST", f.ts.URL+path, strings.NewReader(body))
	if e != nil {
		t.Fatal(e)
	}
	for k, v := range h {
		req.Header.Set(k, v)
	}
	res, e := http.DefaultClient.Do(req)
	if e != nil {
		t.Fatal(e)
	}
	defer res.Body.Close()
	var b map[string]any
	if e = json.NewDecoder(res.Body).Decode(&b); e != nil {
		t.Fatal(e)
	}
	return res.StatusCode, b
}
func TestScopedCaptureProviderAndPolicyMatrix(t *testing.T) {
	for _, metadata := range []bool{false, true} {
		for _, route := range []string{"generic", "claude", "codex", "codex-v2"} {
			for _, scenario := range []string{"valid", "operator", "foreign", "unknown-project", "wrong-op", "bad-secret", "stale", "revoked", "missing", "empty-operator", "bad-operator", "consent", "barrier"} {
				name := route + "/" + scenario
				if metadata {
					name = "v2/" + name
				} else {
					name = "legacy/" + name
				}
				t.Run(name, func(t *testing.T) {
					var meters atomic.Int32
					f := scopedFixture(t, metadata, func() (config.Usage, error) { meters.Add(1); return config.Usage{FreeBytes: 1 << 40}, nil })
					h := f.writer
					project := "p"
					want := 403
					admissionDenied := true
					op := registry.Principal{Kind: registry.Operator}
					switch scenario {
					case "valid":
						want = 200
						admissionDenied = false
					case "operator":
						h = opHdr()
						want = 200
						admissionDenied = false
					case "foreign":
						project = "q"
					case "unknown-project":
						project = "unknown"
					case "wrong-op":
						code, _ := do(t, "POST", f.ts.URL+"/v1/grants", opHdr(), map[string]any{"principal_id": "writer", "kind": "agent", "projects": []string{"p"}, "ops": []string{"search"}, "secret": "fixture-write-only"})
						if code != 201 {
							t.Fatal(code)
						}
						h["X-Grant-Epoch"] = "2"
					case "bad-secret":
						h["X-Secret"] = "wrong"
					case "stale":
						h["X-Grant-Epoch"] = "99"
					case "revoked":
						if e := f.ctl.RevokeGrant(op, "writer"); e != nil {
							t.Fatal(e)
						}
					case "missing":
						h = nil
					case "empty-operator":
						h["X-Operator-Secret"] = ""
						want = 401
					case "bad-operator":
						h["X-Operator-Secret"] = "wrong"
						want = 401
					case "consent":
						provider := "synthetic"
						if route == "claude" {
							provider = "claude-code"
						}
						if route == "codex" {
							provider = "codex-hook-v1"
						}
						if route == "codex-v2" {
							provider = "codex-hook-v2"
						}
						if _, e := f.ctl.SetConsent(op, "p", provider, "capture", false); e != nil {
							t.Fatal(e)
						}
						admissionDenied = false
					case "barrier":
						if _, e := f.ctl.DeleteProjectBarrier(op, "p"); e != nil {
							t.Fatal(e)
						}
						want = 409
						admissionDenied = false
					}
					code, b := scopedRequest(t, f, route, project, h)
					if code != want {
						t.Fatalf("want%d got%d %v", want, code, b)
					}
					if admissionDenied && meters.Load() != 0 {
						t.Fatal("unauthorized request reached meter")
					}
					progress, e := f.ing.Progress()
					if e != nil {
						t.Fatal(e)
					}
					if want == 200 {
						if b["accepted"] != float64(1) || b["committed"] != float64(1) || progress.Accepted != 1 {
							t.Fatal("capture not durably committed", b, progress)
						}
						if scenario == "valid" {
							for _, path := range []string{"/v1/archive/query?project=p", "/v1/whoami?project=p&op=search"} {
								if code, _ := do(t, "GET", f.ts.URL+path, h, nil); code != 403 {
									t.Fatal("capture grant gained read access", code)
								}
							}
							if code, _ := do(t, "POST", f.ts.URL+"/v1/grants", h, map[string]any{}); code != 401 {
								t.Fatal("capture grant gained admin access", code)
							}
						}
					} else if progress.Accepted != 0 {
						t.Fatal("refused request durably accepted", progress)
					}
				})
			}
		}
	}
}

func TestScopedCaptureRechecksAuthorityAfterMeter(t *testing.T) {
	for _, metadata := range []bool{false, true} {
		for _, route := range []string{"generic", "claude", "codex", "codex-v2"} {
			for _, change := range []string{"revoke", "rotate", "consent", "barrier"} {
				name := route + "/" + change
				if metadata {
					name = "v2/" + name
				} else {
					name = "legacy/" + name
				}
				t.Run(name, func(t *testing.T) {
					var mutation func() error
					var ran atomic.Bool
					f := scopedFixture(t, metadata, func() (config.Usage, error) { ran.Store(true); return config.Usage{FreeBytes: 1 << 40}, mutation() })
					op := registry.Principal{Kind: registry.Operator}
					want := 403
					mutation = func() error { return f.ctl.RevokeGrant(op, "writer") }
					if change == "rotate" {
						mutation = func() error {
							return f.ctl.IssueGrant(op, registry.Grant{PrincipalID: "writer", Kind: registry.Agent, Projects: map[string]bool{"p": true}, Ops: map[registry.Op]bool{registry.OpCapture: true}, Secret: "replacement-fixture-secret"})
						}
					}
					if change == "consent" {
						provider := "synthetic"
						if route == "claude" {
							provider = "claude-code"
						}
						if route == "codex" {
							provider = "codex-hook-v1"
						}
						if route == "codex-v2" {
							provider = "codex-hook-v2"
						}
						mutation = func() error { _, e := f.ctl.SetConsent(op, "p", provider, "capture", false); return e }
					}
					if change == "barrier" {
						want = 409
						mutation = func() error { _, e := f.ctl.DeleteProjectBarrier(op, "p"); return e }
					}
					code, b := scopedRequest(t, f, route, "p", f.writer)
					if !ran.Load() || code != want {
						t.Fatalf("in-flight change not enforced: meter%v code%d body%v", ran.Load(), code, b)
					}
					p, e := f.ing.Progress()
					if e != nil || p.Accepted != 0 {
						t.Fatal("changed authority reached durable intake", p, e)
					}
					if metadata {
						state, _, e := f.ctl.ArchiveState("p")
						if e != nil || state.CommittedOrdinal != 0 || state.Pending != nil {
							t.Fatal("denied metadata reservation", state, e)
						}
					}
				})
			}
		}
	}
}

func TestScopedCaptureRefusesDeletedSessionBeforeAcceptance(t *testing.T) {
	for _, metadata := range []bool{false, true} {
		name := "legacy"
		if metadata {
			name = "v2"
		}
		t.Run(name, func(t *testing.T) {
			f := scopedFixture(t, metadata, nil)
			if _, e := f.ctl.DeleteSessionBarrier(registry.Principal{Kind: registry.Operator}, "p", "s"); e != nil {
				t.Fatal(e)
			}
			code, b := scopedRequest(t, f, "generic", "p", f.writer)
			if code != 409 {
				t.Fatalf("deleted session accepted: %d %v", code, b)
			}
			p, e := f.ing.Progress()
			if e != nil || p.Accepted != 0 {
				t.Fatal("deleted payload durably accepted", p, e)
			}
		})
	}
}

func TestScopedCaptureOperatorHeaderTakesPrecedence(t *testing.T) {
	f := scopedFixture(t, false, nil)
	h := map[string]string{"X-Operator-Secret": opSecret, "X-Principal-Id": "absent", "X-Secret": "wrong", "X-Grant-Epoch": "-1"}
	if code, b := scopedRequest(t, f, "generic", "q", h); code != 200 || b["accepted"] != float64(1) {
		t.Fatal("valid operator cannot be demoted by stray agent fields", code, b)
	}
}

func TestScopedCaptureDoesNotExposeMeterDiagnostics(t *testing.T) {
	f := scopedFixture(t, false, func() (config.Usage, error) { return config.Usage{}, fmt.Errorf("private-backend-canary") })
	code, b := scopedRequest(t, f, "generic", "p", f.writer)
	raw, _ := json.Marshal(b)
	if code != 503 || strings.Contains(string(raw), "private-backend-canary") {
		t.Fatal("private diagnostic exposed", code, b)
	}
	code, b = scopedRequest(t, f, "generic", "p", opHdr())
	raw, _ = json.Marshal(b)
	if code != 503 || !strings.Contains(string(raw), "private-backend-canary") {
		t.Fatal("operator diagnostic lost", code, b)
	}
}

func TestScopedCaptureRequiresPost(t *testing.T) {
	for _, path := range []string{"/v1/capture", "/v1/capture/claude-code?project=p&source_instance=i", "/v1/capture/codex-event?project=p&source_instance=i"} {
		t.Run(path, func(t *testing.T) {
			f := scopedFixture(t, false, nil)
			code, _ := do(t, "GET", f.ts.URL+path, f.writer, map[string]any{"project": "p", "provider": "synthetic", "messages": []any{}})
			if code != 405 {
				t.Fatal("capture accepted non-POST", code)
			}
		})
	}
}
