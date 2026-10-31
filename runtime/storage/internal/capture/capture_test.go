package capture

import (
	"strings"
	"testing"

	"aifactory.local/storage/internal/archive"
)

// Generic transport-neutral adapter: prohibited fields are dropped before records exist;
// summaries are typed as summary (never original history).
func TestGenericAdaptRedactsAndTypes(t *testing.T) {
	recs, red := Adapt(ProviderFixture{
		Provider: "synthetic", SourceInstance: "i", Project: "p",
		Messages: []FixtureMessage{
			{SessionID: "s", MessageID: "m1", Seq: 1, Role: "user", Text: "hi", Kind: "message",
				HiddenReasoning: "COT", Secrets: map[string]string{"k": "v"}},
			{SessionID: "s", MessageID: "m2", Seq: 2, Role: "assistant", Text: "sum", Kind: "summary"},
		},
	})
	if len(recs) != 2 {
		t.Fatalf("want 2 records, got %d", len(recs))
	}
	if recs[0].Type != archive.TypeMessage || recs[1].Type != archive.TypeSummary {
		t.Fatalf("summary must be typed TypeSummary: %+v", recs)
	}
	if archive.OriginalHistoryCount(recs) != 1 {
		t.Fatalf("summary must not count as original history")
	}
	if len(red) != 2 {
		t.Fatalf("want hidden_reasoning + secrets redactions, got %v", red)
	}
}

// Provider-specific Claude Code JSONL adapter: a REAL parse of the native format against a
// SYNTHETIC fixture. Thinking + tool internals are redacted; only user-visible text of
// user/assistant messages becomes original history; non-message lines are skipped.
func TestClaudeCodeJSONLAdapter(t *testing.T) {
	fixture := strings.Join([]string{
		`{"type":"user","uuid":"u1","parentUuid":"","sessionId":"sess","message":{"role":"user","content":[{"type":"text","text":"please refactor"}]}}`,
		`{"type":"assistant","uuid":"a1","parentUuid":"u1","sessionId":"sess","message":{"role":"assistant","content":[{"type":"thinking","text":"SECRET REASONING"},{"type":"tool_use","text":"{\"cmd\":\"ls\"}"},{"type":"text","text":"done refactoring"}]}}`,
		`{"type":"summary","summary":"a recap line that must be skipped"}`,
		`{"type":"system","content":"boot"}`,
	}, "\n")

	recs, red, err := AdaptClaudeCodeJSONL([]byte(fixture), "proj-A", "inst-1")
	if err != nil {
		t.Fatalf("parse: %v", err)
	}
	if len(recs) != 2 {
		t.Fatalf("want 2 message records (user + assistant text), got %d: %+v", len(recs), recs)
	}
	if recs[0].Role != "user" || recs[0].Text != "please refactor" {
		t.Fatalf("user message mismatch: %+v", recs[0])
	}
	if recs[1].Role != "assistant" || recs[1].Text != "done refactoring" {
		t.Fatalf("assistant visible text mismatch: %+v", recs[1])
	}
	if recs[1].Provider != "claude-code" || recs[1].ParentID != "u1" || recs[1].SessionID != "sess" {
		t.Fatalf("provenance mismatch: %+v", recs[1])
	}
	// thinking + tool_use must have been redacted (dropped), not captured.
	var droppedThinking, droppedTool bool
	for _, r := range red {
		if r.Field == "thinking" {
			droppedThinking = true
		}
		if r.Field == "tool_use" {
			droppedTool = true
		}
	}
	if !droppedThinking || !droppedTool {
		t.Fatalf("thinking and tool_use must be redacted, got %v", red)
	}
	// No record may carry the hidden-reasoning text.
	for _, r := range recs {
		if strings.Contains(r.Text, "SECRET REASONING") {
			t.Fatalf("hidden reasoning leaked into a record")
		}
	}
}

func TestClaudeCodeJSONLMalformedFailsClosed(t *testing.T) {
	if _, _, err := AdaptClaudeCodeJSONL([]byte("{not json\n"), "p", "i"); err == nil {
		t.Fatalf("a malformed JSONL line must fail closed, not be silently skipped")
	}
}
