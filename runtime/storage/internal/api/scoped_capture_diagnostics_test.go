package api_test

import (
	"aifactory.local/storage/internal/archive"
	"aifactory.local/storage/internal/config"
	"fmt"
	"strings"
	"testing"
)

type privateCaptureFailure struct{ *archive.MemStore }

func (s *privateCaptureFailure) Put(archive.Record) error { return fmt.Errorf("private-source-canary") }
func (s *privateCaptureFailure) PutEnvelope(archive.Envelope) error {
	return fmt.Errorf("private-source-canary")
}
func TestScopedCaptureHidesSourceDiagnostics(t *testing.T) {
	for _, metadata := range []bool{false, true} {
		name := "legacy"
		if metadata {
			name = "v2"
		}
		t.Run(name, func(t *testing.T) {
			f := scopedFixture(t, metadata, nil, &privateCaptureFailure{archive.NewMemStore()})
			field := "drain_error"
			want := 200
			if metadata {
				field = "error"
				want = 503
			}
			code, b := scopedRequest(t, f, "generic", "p", f.writer)
			if code != want || b[field] != "capture unavailable; inspect receipts before retry" {
				t.Fatal("scoped source diagnostics leaked", code, b)
			}
			code, b = scopedRequest(t, f, "generic", "p", opHdr())
			if code != want || !strings.Contains(fmt.Sprint(b[field]), "private-source-canary") {
				t.Fatal("operator diagnostic lost", code, b)
			}
		})
	}
}
func TestScopedCaptureHidesAdmissionDiagnostics(t *testing.T) {
	f := scopedFixture(t, false, func() (config.Usage, error) { return config.Usage{}, nil })
	code, b := scopedRequest(t, f, "generic", "p", f.writer)
	if code != 503 || b["error"] != "capture unavailable; inspect receipts before retry" {
		t.Fatal("admission details exposed", code, b)
	}
}
func TestScopedCaptureConflictRemainsConflictWithoutBackendDetails(t *testing.T) {
	f := scopedFixture(t, false, nil)
	if code, b := scopedRequest(t, f, "generic", "p", f.writer); code != 200 {
		t.Fatal(code, b)
	}
	code, b := do(t, "POST", f.ts.URL+"/v1/capture", f.writer, map[string]any{"project": "p", "provider": "synthetic", "source_instance": "fixture", "messages": []map[string]any{{"session_id": "s", "message_id": "m", "text": "changed"}}})
	if code != 409 || b["error"] != "capture unavailable; inspect receipts before retry" {
		t.Fatal("conflict status or diagnostic", code, b)
	}
}
