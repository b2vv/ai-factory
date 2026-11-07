package api_test

import (
	"aifactory.local/storage/internal/archive"
	"aifactory.local/storage/internal/registry"
	"net/http"
	"strings"
	"testing"
)

func TestScopedCaptureAcceptsOwnProject(t *testing.T) {
	ts, _, _, _ := captureServer(t, archive.NewMemStore(), nil)
	if code, _ := do(t, http.MethodPost, ts.URL+"/v1/projects", opHdr(), map[string]string{"UUID": "p"}); code != 201 {
		t.Fatal(code)
	}
	if code, _ := do(t, http.MethodPost, ts.URL+"/v1/consent", opHdr(), map[string]any{"Project": "p", "Provider": "synthetic", "Capability": "capture", "Enabled": true}); code != 200 {
		t.Fatal(code)
	}
	code, g := do(t, http.MethodPost, ts.URL+"/v1/grants", opHdr(), map[string]any{"principal_id": "writer", "kind": "agent", "projects": []string{"p"}, "ops": []string{"capture"}, "secret": "fixture-write-only"})
	if code != 201 {
		t.Fatal(code, g)
	}
	h := map[string]string{"X-Principal-Id": "writer", "X-Grant-Epoch": itoa(int64(g["epoch"].(float64))), "X-Secret": "fixture-write-only"}
	code, b := do(t, http.MethodPost, ts.URL+"/v1/capture", h, map[string]any{"project": "p", "provider": "synthetic", "source_instance": "fixture", "messages": []map[string]any{{"session_id": "s", "message_id": "m", "text": "hello"}}})
	if code != 200 || b["accepted"] != float64(1) || b["committed"] != float64(1) {
		t.Fatalf("scoped capture: %d %v", code, b)
	}
}

func TestCodexV2ContinuedSnapshotsAndLegacyCoexist(t *testing.T) {
	store := archive.NewMemStore()
	f := scopedFixture(t, false, nil, store)
	op := registry.Principal{Kind: registry.Operator}
	if _, err := f.ctl.SetConsent(op, "p", "codex-hook-v2", "capture", true); err != nil {
		t.Fatal(err)
	}
	post := func(path string, ev map[string]any, want int) map[string]any {
		t.Helper()
		code, b := do(t, "POST", f.ts.URL+path+"?project=p&source_instance=fixture", f.writer, ev)
		if code != want {
			t.Fatalf("capture: want %d got %d %v", want, code, b)
		}
		return b
	}
	prompt := map[string]any{"schema_version": 2, "hook_event_name": "UserPromptSubmit", "session_id": "s", "turn_id": "turn", "prompt": "question"}
	stop := map[string]any{"schema_version": 2, "hook_event_name": "Stop", "session_id": "s", "turn_id": "turn", "last_assistant_message": "first snapshot", "stop_hook_active": false}
	path := "/v1/capture/codex-event-v2"
	post(path, prompt, 200)
	post(path, stop, 200)
	stop["last_assistant_message"] = "continued snapshot"
	stop["stop_hook_active"] = true
	post(path, stop, 200)
	n := f.ing.AcceptedBytes()
	post(path, stop, 200)
	stop["stop_hook_active"] = false
	post(path, stop, 200)
	if f.ing.AcceptedBytes() != n {
		t.Fatal("identical snapshot replay appended")
	}
	delete(prompt, "schema_version")
	post("/v1/capture/codex-event", prompt, 200)
	records, err := store.Fetch("p")
	if err != nil || len(records) != 4 {
		t.Fatalf("v1/v2 coexist: %d %v", len(records), err)
	}
	texts := map[string]bool{}
	for _, r := range records {
		texts[r.Text] = true
		if r.Role == "assistant" && r.ParentID != "v2/turn/prompt" {
			t.Fatal("wrong snapshot parent")
		}
	}
	if !texts["first snapshot"] || !texts["continued snapshot"] {
		t.Fatal("continued Stop lost")
	}
}

func TestCodexV2AcknowledgesOnlyTheSnapshotContract(t *testing.T) {
	f := scopedFixture(t, false, nil)
	op := registry.Principal{Kind: registry.Operator}
	if _, err := f.ctl.SetConsent(op, "p", "codex-hook-v2", "capture", true); err != nil {
		t.Fatal(err)
	}
	req, err := http.NewRequest("POST", f.ts.URL+"/v1/capture/codex-event-v2?project=p&source_instance=fixture", strings.NewReader(`{"schema_version":2,"hook_event_name":"Stop","session_id":"s","turn_id":"t","last_assistant_message":"visible","stop_hook_active":true}`))
	if err != nil {
		t.Fatal(err)
	}
	for k, v := range f.writer {
		req.Header.Set(k, v)
	}
	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		t.Fatal(err)
	}
	defer resp.Body.Close()
	if resp.StatusCode != 200 || resp.Header.Get("X-AF-Codex-Contract") != "2" {
		t.Fatal("missing contract acknowledgement", resp.StatusCode, resp.Header)
	}
}
