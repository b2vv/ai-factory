package capture

import (
	"aifactory.local/storage/internal/archive"
	"encoding/json"
	"reflect"
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

func TestCodexV2ShapeAndSanitizedSnapshotIdentity(t *testing.T) {
	valid := map[string]any{"schema_version": 2, "hook_event_name": "Stop", "session_id": "session", "turn_id": "turn", "last_assistant_message": "password=first-private", "stop_hook_active": false}
	adapt := func(ev map[string]any) ([]archive.Record, []Redaction, error) {
		b, _ := json.Marshal(ev)
		return AdaptCodexSnapshotEvent(b, "p", "source")
	}
	first, red, err := adapt(valid)
	if err != nil || len(first) != 1 || len(red) != 1 {
		t.Fatal(err)
	}
	expected := "v2/turn/assistant/35b1ed223d727f62b720c833730b496a6b78b9cca427cbbf910115bd286cf055"
	if first[0].MessageID != expected || first[0].Text != RedactedText || red[0].MessageID != expected || first[0].Provider != "codex-hook-v2" {
		t.Fatal("sanitized identity", first, red)
	}
	valid["last_assistant_message"] = "password=other-private"
	valid["stop_hook_active"] = true
	second, _, err := adapt(valid)
	if err != nil || !reflect.DeepEqual(first, second) {
		t.Fatal("redacted replay identity changed")
	}
	for _, version := range []any{nil, 1, 3, true, "2", 2.5} {
		valid["schema_version"] = version
		if _, _, err := adapt(valid); err == nil {
			t.Fatalf("invalid version accepted: %v", version)
		}
	}
	valid["schema_version"] = 2
	for _, flag := range []any{nil, 1, "false", []any{}, map[string]any{}} {
		valid["stop_hook_active"] = flag
		if _, _, err := adapt(valid); err == nil {
			t.Fatalf("invalid Stop flag accepted: %v", flag)
		}
	}
	delete(valid, "stop_hook_active")
	if _, _, err := adapt(valid); err == nil {
		t.Fatal("missing Stop flag accepted")
	}
	valid["hook_event_name"] = "UserPromptSubmit"
	delete(valid, "last_assistant_message")
	valid["prompt"] = "question"
	records, _, err := adapt(valid)
	if err != nil || records[0].MessageID != "v2/turn/prompt" || records[0].ParentID != "" {
		t.Fatal("v2 prompt", records, err)
	}
	valid["stop_hook_active"] = nil
	if _, _, err := adapt(valid); err == nil {
		t.Fatal("prompt with Stop flag accepted")
	}
}

func TestCodexV2RejectsUnsupportedRawShapes(t *testing.T) {
	for _, raw := range []string{
		`{}`, `null`, `{`,
		`{"schema_version":2.0,"hook_event_name":"Stop","session_id":"s","turn_id":"t","last_assistant_message":"text","stop_hook_active":false}`,
		`{"schema_version":2e0,"hook_event_name":"Stop","session_id":"s","turn_id":"t","last_assistant_message":"text","stop_hook_active":false}`,
		`{"schema_version":2,"hook_event_name":"SubagentStop","session_id":"s","turn_id":"t","last_assistant_message":"text","stop_hook_active":false}`,
		`{"schema_version":2,"hook_event_name":"Stop","session_id":"s","turn_id":"t","last_assistant_message":"","stop_hook_active":false}`,
		`{"schema_version":2,"hook_event_name":"Stop","session_id":"s","turn_id":"t","last_assistant_message":"text","prompt":"text","stop_hook_active":false}`,
	} {
		if _, _, err := AdaptCodexSnapshotEvent([]byte(raw), "p", "i"); err == nil {
			t.Fatalf("unsupported raw shape accepted: %s", raw)
		}
	}
	raw := `{"schema_version":2,"hook_event_name":"Stop","session_id":"s","turn_id":"t","last_assistant_message":"visible","stop_hook_active":true,"transcript_path":"DO_NOT_READ","hidden_reasoning":"PRIVATE_CANARY"}`
	recs, _, err := AdaptCodexSnapshotEvent([]byte(raw), "p", "i")
	if err != nil {
		t.Fatal(err)
	}
	serialized, _ := json.Marshal(recs)
	if strings.Contains(string(serialized), "DO_NOT_READ") || strings.Contains(string(serialized), "PRIVATE_CANARY") {
		t.Fatal("prohibited fields copied")
	}
}
