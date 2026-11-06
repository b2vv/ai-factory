package api_test

import (
	"aifactory.local/storage/internal/archive"
	"encoding/json"
	"net/http"
	"strings"
	"testing"
)

func TestScopedCaptureRejectsAmbiguousCredentials(t *testing.T) {
	for _, header := range []string{"X-Operator-Secret", "X-Principal-Id", "X-Secret", "X-Grant-Epoch"} {
		t.Run(header, func(t *testing.T) {
			ts, _, i, _ := captureServer(t, archive.NewMemStore(), nil)
			do(t, "POST", ts.URL+"/v1/projects", opHdr(), map[string]string{"UUID": "p"})
			do(t, "POST", ts.URL+"/v1/consent", opHdr(), map[string]any{"Project": "p", "Provider": "synthetic", "Capability": "capture", "Enabled": true})
			code, g := do(t, "POST", ts.URL+"/v1/grants", opHdr(), map[string]any{"principal_id": "writer", "kind": "agent", "projects": []string{"p"}, "ops": []string{"capture"}, "secret": "fixture-write-only"})
			if code != 201 {
				t.Fatal(code, g)
			}
			req, _ := http.NewRequest("POST", ts.URL+"/v1/capture", strings.NewReader(`{"project":"p","provider":"synthetic","source_instance":"i","messages":[{"session_id":"s","message_id":"m","text":"denied"}]}`))
			req.Header.Set("X-Principal-Id", "writer")
			req.Header.Set("X-Grant-Epoch", itoa(int64(g["epoch"].(float64))))
			req.Header.Set("X-Secret", "fixture-write-only")
			if header == "X-Operator-Secret" {
				req.Header.Set(header, opSecret)
			}
			req.Header.Add(header, "conflicting-second-value")
			resp, err := http.DefaultClient.Do(req)
			if err != nil {
				t.Fatal(err)
			}
			defer resp.Body.Close()
			var body map[string]any
			json.NewDecoder(resp.Body).Decode(&body)
			if resp.StatusCode != 400 {
				t.Fatalf("ambiguous auth accepted: %d %v", resp.StatusCode, body)
			}
			progress, err := i.Progress()
			if err != nil || progress.Accepted != 0 {
				t.Fatal("denied request reached durable intake", progress, err)
			}
		})
	}
}
