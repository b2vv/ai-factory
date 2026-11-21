package capture

import (
	"crypto/sha256"
	"encoding/json"
	"errors"
	"fmt"
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

// CodexSnapshotProvider is an opt-in contract for distinct sanitized Stop snapshots.
// Provider is not part of archive identity: v2 IDs are separately namespaced.
const CodexSnapshotProvider = "codex-hook-v2"

// AdaptCodexSnapshotEvent preserves all distinct Stop texts, including continuations.
// It cannot determine which concurrent Stop callback ends a turn. Seq remains a
// role position, not callback order. The flag validates the native shape only and
// never alters immutable record content for an otherwise identical snapshot.
func AdaptCodexSnapshotEvent(data []byte, project, sourceInstance string) ([]archive.Record, []Redaction, error) {
	var shape struct {
		Version int             `json:"schema_version"`
		Event   string          `json:"hook_event_name"`
		Active  json.RawMessage `json:"stop_hook_active"`
	}
	if json.Unmarshal(data, &shape) != nil || shape.Version != 2 {
		return nil, nil, errors.New("Codex snapshot schema_version must be integer 2")
	}
	switch shape.Event {
	case "Stop":
		var active bool
		if len(shape.Active) == 0 || string(shape.Active) == "null" || json.Unmarshal(shape.Active, &active) != nil {
			return nil, nil, errors.New("Codex snapshot Stop requires boolean stop_hook_active")
		}
	case "UserPromptSubmit":
		if len(shape.Active) != 0 {
			return nil, nil, errors.New("Codex snapshot prompt cannot carry stop_hook_active")
		}
	default:
		return nil, nil, errors.New("unsupported Codex snapshot event")
	}
	records, red, err := AdaptCodexEvent(data, project, sourceInstance)
	if err != nil {
		return nil, nil, err
	}
	rec := &records[0]
	rec.Provider = CodexSnapshotProvider
	rec.MessageID = "v2/" + rec.MessageID
	if rec.Role == "assistant" {
		digest := sha256.Sum256([]byte(rec.Text))
		rec.MessageID += fmt.Sprintf("/%x", digest)
		rec.ParentID = "v2/" + rec.ParentID
	}
	for i := range red {
		red[i].MessageID = rec.MessageID
	}
	return records, red, nil
}
