// Package capture adapts a provider's conversation data into archive records. In this
// phase it consumes SYNTHETIC provider fixtures only (no real transcript reads, no private
// stores); real per-provider adapters remain NOT_TESTED and separately authorized (PLAN
// §11.2, AF3). The adapter applies fail-closed redaction BEFORE any record exists:
//   - hidden reasoning is NEVER emitted (P5);
//   - prohibited/secret fields are dropped before the record is created, so they can never
//     reach a durable queue (P4);
//   - summaries are typed as TypeSummary and NEVER counted as original history (D5/AF2).
//
// The adapter does not itself enforce consent or deletion barriers; those are gated by the
// caller BEFORE acceptance (see the API capture handler).
package capture

import (
	"aifactory.local/storage/internal/archive"
	"time"
)

// ProviderFixture is a synthetic, provider-shaped input. It is NOT a real transcript.
type ProviderFixture struct {
	Provider       string           `json:"provider"`
	SourceInstance string           `json:"source_instance"`
	Project        string           `json:"project"`
	Messages       []FixtureMessage `json:"messages"`
}

// FixtureMessage is one synthetic message. Fields that are prohibited from capture are
// present in the fixture shape only so the adapter can demonstrably DROP them.
type FixtureMessage struct {
	SourceEventTime *time.Time `json:"source_event_time,omitempty"`
	SessionID       string     `json:"session_id"`
	MessageID       string     `json:"message_id"`
	Seq             int        `json:"seq"`
	ParentID        string     `json:"parent_id"`
	Role            string     `json:"role"` // "user" | "assistant"
	Text            string     `json:"text"`
	Kind            string     `json:"kind"` // "message" (original history) | "summary" (interim)
	Edited          bool       `json:"edited"`
	Withdrawn       bool       `json:"withdrawn"`

	// Prohibited fields (P4/P5): MUST be dropped by the adapter before any record exists.
	HiddenReasoning string            `json:"hidden_reasoning,omitempty"`
	Secrets         map[string]string `json:"secrets,omitempty"`
}

// Redaction records WHAT was dropped (never the values), for an observable audit.
type Redaction struct {
	MessageID string `json:"message_id"`
	Field     string `json:"field"` // e.g. "hidden_reasoning", "secrets"
}

func recordType(kind string) archive.RecordType {
	if kind == "summary" {
		return archive.TypeSummary
	}
	return archive.TypeMessage
}

// Adapt converts a synthetic fixture into archive records, dropping prohibited fields first.
// It returns the records and the list of redactions performed (fields only, no values).
func Adapt(f ProviderFixture) ([]archive.Record, []Redaction) {
	var recs []archive.Record
	var red []Redaction
	for _, m := range f.Messages {
		if m.HiddenReasoning != "" {
			red = append(red, Redaction{MessageID: m.MessageID, Field: "hidden_reasoning"})
		}
		if len(m.Secrets) > 0 {
			red = append(red, Redaction{MessageID: m.MessageID, Field: "secrets"})
		}
		text, withheld := SanitizeText(m.Text)
		if withheld {
			red = append(red, Redaction{MessageID: m.MessageID, Field: SanitizerVersion})
		}
		// The record is built WITHOUT the prohibited fields; they never enter the record and
		// therefore never reach the WAL/archive.
		recs = append(recs, archive.Record{
			Project:        f.Project,
			Provider:       f.Provider,
			SourceInstance: f.SourceInstance,
			SessionID:      m.SessionID,
			MessageID:      m.MessageID,
			Seq:            m.Seq,
			ParentID:       m.ParentID,
			Type:           recordType(m.Kind),
			Role:           m.Role,
			Text:           text,
			Edited:         m.Edited,
			Withdrawn:      m.Withdrawn,
		})
	}
	return recs, red
}
