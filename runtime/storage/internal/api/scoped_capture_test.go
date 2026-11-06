package api_test

import (
	"aifactory.local/storage/internal/archive"
	"net/http"
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
