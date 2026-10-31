// Provider-specific capture adapter for the Claude Code session transcript (JSONL).
//
// This is a REAL parser of a provider's native on-disk format, distinct from the
// transport-neutral ProviderFixture path in capture.go. It is exercised in this phase only
// against SYNTHETIC fixtures of this format (no real transcript is read); fidelity to a real
// Claude Code transcript is NOT_TESTED and the exact upstream schema is NOT a verified
// contract here - see PROVIDER-ADAPTER-JUSTIFICATION.md. Other providers are NOT_IMPLEMENTED.
//
// Format (assumed public shape): one JSON object per line. Relevant fields:
//
//	{"type":"user"|"assistant", "uuid":"...", "parentUuid":"...", "sessionId":"...",
//	 "message":{"role":"user"|"assistant",
//	            "content": [ {"type":"text","text":"..."},
//	                         {"type":"thinking", ...},        // hidden reasoning - DROPPED (P5)
//	                         {"type":"tool_use", ...},         // internal - DROPPED
//	                         {"type":"tool_result", ...} ] }}  // internal - DROPPED
//
// Only user-visible text blocks of user/assistant messages are captured as original history;
// thinking and tool internals are redacted BEFORE a record exists. Lines that are not
// user/assistant messages (summaries, meta, system) are skipped (summaries are never
// original history, D5). Malformed lines fail the parse (fail-closed), never silently.
package capture

import (
	"bufio"
	"bytes"
	"encoding/json"
	"fmt"
	"strings"

	"aifactory.local/storage/internal/archive"
)

type ccLine struct {
	Type       string `json:"type"`
	UUID       string `json:"uuid"`
	ParentUUID string `json:"parentUuid"`
	SessionID  string `json:"sessionId"`
	Message    struct {
		Role    string `json:"role"`
		Content []struct {
			Type string `json:"type"`
			Text string `json:"text"`
		} `json:"content"`
	} `json:"message"`
}

// AdaptClaudeCodeJSONL parses a synthetic Claude Code transcript (JSONL) into archive
// records for a project, redacting hidden reasoning and tool internals before any record
// exists. It returns the records, the redactions performed (block types dropped; no values),
// and an error for a malformed line (fail-closed).
func AdaptClaudeCodeJSONL(data []byte, project, sourceInstance string) ([]archive.Record, []Redaction, error) {
	var recs []archive.Record
	var red []Redaction
	sc := bufio.NewScanner(bytes.NewReader(data))
	sc.Buffer(make([]byte, 0, 64*1024), 8*1024*1024)
	seq := 0
	for lineNo := 1; sc.Scan(); lineNo++ {
		raw := bytes.TrimSpace(sc.Bytes())
		if len(raw) == 0 {
			continue
		}
		var l ccLine
		if err := json.Unmarshal(raw, &l); err != nil {
			return nil, nil, fmt.Errorf("claude-code JSONL line %d: malformed: %w", lineNo, err)
		}
		if l.Type != "user" && l.Type != "assistant" {
			continue // not an original user/assistant message (meta/summary/system): skip
		}
		var parts []string
		for _, c := range l.Message.Content {
			switch c.Type {
			case "text":
				if c.Text != "" {
					parts = append(parts, c.Text)
				}
			case "thinking":
				red = append(red, Redaction{MessageID: l.UUID, Field: "thinking"})
			case "tool_use", "tool_result":
				red = append(red, Redaction{MessageID: l.UUID, Field: c.Type})
			default:
				red = append(red, Redaction{MessageID: l.UUID, Field: "content:" + c.Type})
			}
		}
		if len(parts) == 0 {
			continue // nothing user-visible after redaction
		}
		seq++
		recs = append(recs, archive.Record{
			Project:        project,
			Provider:       "claude-code",
			SourceInstance: sourceInstance,
			SessionID:      l.SessionID,
			MessageID:      l.UUID,
			Seq:            seq,
			ParentID:       l.ParentUUID,
			Type:           archive.TypeMessage,
			Role:           l.Message.Role,
			Text:           strings.Join(parts, "\n"),
		})
	}
	if err := sc.Err(); err != nil {
		return nil, nil, fmt.Errorf("claude-code JSONL scan: %w", err)
	}
	return recs, red, nil
}
