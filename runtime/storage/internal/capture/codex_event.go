package capture

import (
	"encoding/json"
	"errors"
	"regexp"

	"aifactory.local/storage/internal/archive"
)

// CodexEventProvider identifies an explicit subset of documented lifecycle events.
// It does not imply installed hooks, a complete transcript, or native Markdown support.
const CodexEventProvider = "codex-hook-v1"

var eventID = regexp.MustCompile(`^[A-Za-z0-9_-]{1,160}$`)

// AdaptCodexEvent consumes only documented prompt/last-assistant fields. It never
// opens transcript_path, follows cwd, copies tool payloads, or reconstructs history.
// SourceInstance and project are explicit operator mappings, not inferred from input.
func AdaptCodexEvent(data []byte, project, sourceInstance string) ([]archive.Record, []Redaction, error) {
	var e struct {
		Event     string  `json:"hook_event_name"`
		Session   string  `json:"session_id"`
		Turn      string  `json:"turn_id"`
		Prompt    *string `json:"prompt"`
		Assistant *string `json:"last_assistant_message"`
	}
	if json.Unmarshal(data, &e) != nil {
		return nil, nil, errors.New("invalid Codex event JSON")
	}
	if project == "" || sourceInstance == "" || !eventID.MatchString(e.Session) || !eventID.MatchString(e.Turn) {
		return nil, nil, errors.New("Codex event requires project, source instance and supported session/turn identifiers")
	}
	var text, role, suffix, parent string
	var seq int
	switch e.Event {
	case "UserPromptSubmit":
		if e.Prompt == nil || e.Assistant != nil {
			return nil, nil, errors.New("unsupported Codex prompt event shape")
		}
		text, role, suffix, seq = *e.Prompt, "user", "prompt", 1
	case "Stop":
		if e.Assistant == nil || e.Prompt != nil {
			return nil, nil, errors.New("Codex stop has no supported assistant text; record a gap")
		}
		text, role, suffix, parent, seq = *e.Assistant, "assistant", "assistant", e.Turn+"/prompt", 2
	default:
		return nil, nil, errors.New("unsupported Codex lifecycle event")
	}
	if text == "" {
		return nil, nil, errors.New("empty Codex event text; record a gap")
	}
	clean, withheld := SanitizeText(text)
	id := e.Turn + "/" + suffix
	var red []Redaction
	if withheld {
		red = append(red, Redaction{MessageID: id, Field: SanitizerVersion})
	}
	return []archive.Record{{Project: project, Provider: CodexEventProvider, SourceInstance: sourceInstance, SessionID: e.Session, MessageID: id, ParentID: parent, Seq: seq, Role: role, Type: archive.TypeMessage, Text: clean}}, red, nil
}
