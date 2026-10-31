package capture

import (
	"encoding/json"
	"strings"
	"testing"
)

func TestCodexDocumentedEventsOnly(t *testing.T) {
	raw := `{"hook_event_name":"Stop","session_id":"thr_test","turn_id":"turn_test","last_assistant_message":"Decision: retain source provenance","transcript_path":"/DO-NOT-OPEN","hidden_reasoning":"hidden-canary"}`
	recs, _, err := AdaptCodexEvent([]byte(raw), "p", "source")
	if err != nil || len(recs) != 1 || recs[0].MessageID != "turn_test/assistant" || recs[0].ParentID != "turn_test/prompt" {
		t.Fatal("provenance missing")
	}
	b, _ := json.Marshal(recs)
	if strings.Contains(string(b), "canary") || strings.Contains(string(b), "DO-NOT-OPEN") {
		t.Fatal("prohibited fields copied")
	}
	for _, bad := range []string{`{}`, `{"hook_event_name":"Stop","session_id":"s","turn_id":"t","last_assistant_message":null}`, `{"hook_event_name":"SessionEnd","session_id":"s","turn_id":"t"}`, `{"hook_event_name":"Stop","session_id":"s","turn_id":"t","last_assistant_message":"x","prompt":"y"}`} {
		if r, _, e := AdaptCodexEvent([]byte(bad), "p", "i"); e == nil || r != nil {
			t.Fatal("unsupported shape accepted")
		}
	}
	r, red, e := AdaptCodexEvent([]byte(`{"hook_event_name":"UserPromptSubmit","session_id":"s","turn_id":"t","prompt":"password=synthetic-canary"}`), "p", "i")
	if e != nil || r[0].Text != RedactedText || len(red) != 1 {
		t.Fatal("known credential not withheld")
	}
}
