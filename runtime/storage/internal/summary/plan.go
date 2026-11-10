// Package summary plans local derived aids. It does not run a model, write source
// data or establish native-capture completeness.
package summary

import (
	"aifactory.local/storage/internal/archive"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"sort"
	"time"
	"unicode/utf8"
)

type Scope struct {
	Project        string `json:"project"`
	Provider       string `json:"provider"`
	SourceInstance string `json:"source_instance"`
	SessionID      string `json:"session_id"`
	Branch         string `json:"branch"`
	BranchKnown    bool   `json:"branch_known"`
}
type Baseline struct {
	Project, Generation string
	Ordinal             int64
	At                  time.Time
}
type Config struct {
	ActiveAfter, IdleAfter                                time.Duration
	MaxInputBytes, MaxObservationBytes, MaxReferenceBytes int
	Version                                               string
}

func DefaultConfig() Config {
	return Config{30 * time.Minute, 15 * time.Minute, 256 << 10, 8 << 20, 256 << 10, "summary-config/1"}
}

// Validate admits runtime settings without inventing a session or reading data.
func (c Config) Validate() error {
	if c.ActiveAfter <= 0 || c.IdleAfter <= 0 || c.MaxInputBytes <= 0 || c.MaxInputBytes > 8<<20 || c.MaxObservationBytes < c.MaxInputBytes || c.MaxObservationBytes > 32<<20 || c.MaxReferenceBytes <= 0 || c.MaxReferenceBytes > 1<<20 || !bounded(c.Version, 256) {
		return errors.New("summary: invalid configuration")
	}
	return nil
}

type Identity struct {
	Project        string `json:"project"`
	SourceInstance string `json:"source_instance"`
	SessionID      string `json:"session_id"`
	MessageID      string `json:"message_id"`
}
type SourceRef struct {
	Identity     Identity         `json:"identity"`
	Provider     string           `json:"provider"`
	ParentID     string           `json:"parent_id"`
	ConsentEpoch int64            `json:"consent_epoch"`
	RecordHash   string           `json:"record_hash"`
	EnvelopeHash string           `json:"envelope_hash"`
	Metadata     archive.Metadata `json:"metadata"`
}

// Progress is caller-verified historical processing, never serving permission.
type Progress struct {
	AfterOrdinal  int64  `json:"after_ordinal"`
	PreviousJobID string `json:"previous_job_id"`
}

type Manifest struct {
	Progress            *Progress   `json:"progress,omitempty"`
	PendingOriginals    int         `json:"pending_observed_originals"`
	Format              string      `json:"format"`
	Scope               Scope       `json:"scope"`
	Generation          string      `json:"generation"`
	ObservedCutoff      int64       `json:"observed_cutoff"`
	ActivationOrdinal   int64       `json:"activation_ordinal"`
	GeneratorVersion    string      `json:"generator_version"`
	Config              Config      `json:"config"`
	Sources             []SourceRef `json:"sources"`
	CaptureCompleteness string      `json:"capture_completeness"`
}
type Input struct {
	Progress         *Progress
	Covered          []SourceRef
	Scope            Scope
	Generation       string
	Cutoff           int64
	Complete         bool
	Activation       *Baseline
	ClockFloor       time.Time
	GeneratorVersion string
	Messages         []archive.Envelope
}
type Decision struct {
	Manifest     Manifest
	EvidenceHash string
	Ready        bool
	Reason       string
	NextDue      *time.Time
	JobID        string
	Selected     []archive.Envelope
}

func digest(v any) string {
	b, _ := json.Marshal(v)
	h := sha256.Sum256(b)
	return hex.EncodeToString(h[:])
}
func Plan(c Config, now time.Time, in Input) (Decision, error) {
	if in.Progress != nil {
		detached := *in.Progress
		in.Progress = &detached
	}
	canonical, err := validate(c, now, in)
	if err != nil {
		return Decision{}, err
	}
	in.Messages = canonical
	actual := map[string]SourceRef{}
	for _, e := range canonical {
		if e.Record.Type == archive.TypeMessage {
			actual[archive.IdentityKey(e.Record)] = reference(e)
		}
	}
	covered := map[string]bool{}

	if len(in.Covered) > 0 {
		if len(in.Covered) > c.MaxReferenceBytes/2 {
			return Decision{}, errors.New("summary: coverage reference budget exceeded")
		}
		used := 2
		for index, ref := range in.Covered {
			id := ref.Identity
			if !bounded(id.Project, 4096) || !bounded(id.SourceInstance, 4096) || !bounded(id.SessionID, 4096) || !bounded(id.MessageID, 4096) || !bounded(ref.Provider, 256) || len(ref.ParentID) > 4096 || !utf8.ValidString(ref.ParentID) || len(ref.RecordHash) != 64 || len(ref.EnvelopeHash) != 64 || !bounded(ref.Metadata.Generation, 128) {
				return Decision{}, errors.New("summary: invalid coverage reference")
			}
			if !stringsFit(c.MaxReferenceBytes-used, id.Project, id.SourceInstance, id.SessionID, id.MessageID, ref.Provider, ref.ParentID, ref.RecordHash, ref.EnvelopeHash, ref.Metadata.Generation) {
				return Decision{}, errors.New("summary: coverage reference budget exceeded")
			}
			if ref.Metadata.CapturedAt != nil {
				if !validTime(*ref.Metadata.CapturedAt) || now.Before(*ref.Metadata.CapturedAt) {
					return Decision{}, errors.New("summary: invalid coverage time")
				}
				v := ref.Metadata.CapturedAt.UTC()
				ref.Metadata.CapturedAt = &v
			}
			if ref.Metadata.SourceEventTime != nil {
				v := ref.Metadata.SourceEventTime.UTC()
				ref.Metadata.SourceEventTime = &v
			}
			raw, err := json.Marshal(ref)
			cost := len(raw)
			if index > 0 {
				cost++
			}
			if err != nil || cost > c.MaxReferenceBytes-used {
				return Decision{}, errors.New("summary: coverage reference budget or format")
			}
			used += cost
			r := archive.Record{Project: id.Project, SourceInstance: id.SourceInstance, SessionID: id.SessionID, MessageID: id.MessageID}
			key := archive.IdentityKey(r)
			got, ok := actual[key]
			if !ok || digest(got) != digest(ref) {
				return Decision{}, errors.New("summary: stale coverage requires revalidation")
			}
			covered[key] = true
		}
	}

	if !in.Complete {
		return Decision{Reason: "incomplete"}, nil
	}
	after := in.Activation.Ordinal
	if in.Progress != nil {
		after = in.Progress.AfterOrdinal
	}
	var selected []archive.Envelope
	var first, last time.Time
	for _, e := range in.Messages {
		if e.Record.Type != archive.TypeMessage || e.Metadata.Ordinal <= after || covered[archive.IdentityKey(e.Record)] {
			continue
		}
		at := *e.Metadata.CapturedAt
		if len(selected) == 0 || at.Before(first) {
			first = at
		}
		if len(selected) == 0 || at.After(last) {
			last = at
		}
		selected = append(selected, e)
	}
	if len(selected) == 0 {
		return Decision{Reason: "no_new_messages"}, nil
	}

	due := last.Add(c.IdleAfter)
	active := first.Add(c.ActiveAfter)
	if !validTime(due) || !validTime(active) {
		return Decision{}, errors.New("summary: deadline overflow")
	}
	reason := "idle"
	if active.Before(due) {
		due = active
		reason = "active"
	}
	total := 0
	prefixBytes := 0
	prefix := 0
	for _, e := range selected {
		raw, err := archive.EncodeEnvelope(e)
		if err != nil {
			return Decision{}, err
		}
		cost := len(raw) + 1
		total += cost
		if prefix == 0 && cost > c.MaxInputBytes {
			return Decision{}, errors.New("summary: oversized first record; chunking required")
		}
		if prefixBytes+cost <= c.MaxInputBytes && prefixBytes == total-cost {
			prefixBytes += cost
			prefix++
		}
	}
	pending := len(selected) - prefix
	if total >= c.MaxInputBytes {
		reason = "size"
		due = now
	} else if now.Before(due) {
		return Decision{Reason: "waiting", NextDue: &due}, nil
	}
	selected = selected[:prefix:prefix]

	refs := make([]SourceRef, 0, len(selected))
	for _, e := range selected {
		refs = append(refs, reference(e))
	}
	encoded, err := json.Marshal(refs)
	if err != nil || len(encoded) > c.MaxReferenceBytes {
		return Decision{}, errors.New("summary: coverage reference budget exceeded")
	}
	manifest := Manifest{Progress: in.Progress, PendingOriginals: pending, Format: "ai-factory.summary-coverage/1", Scope: in.Scope, Generation: in.Generation, ObservedCutoff: in.Cutoff, ActivationOrdinal: in.Activation.Ordinal, GeneratorVersion: in.GeneratorVersion, Config: c, Sources: refs, CaptureCompleteness: "unknown"}
	key := jobIdentity(manifest)
	return Decision{Ready: true, Reason: reason, NextDue: &due, Selected: selected, Manifest: manifest, EvidenceHash: digest(manifest), JobID: key}, nil
}

func bounded(v string, max int) bool { return v != "" && len(v) <= max && utf8.ValidString(v) }
func validTime(v time.Time) bool {
	if v.IsZero() {
		return false
	}
	_, e := v.UTC().MarshalJSON()
	return e == nil
}
func validate(c Config, now time.Time, in Input) ([]archive.Envelope, error) {
	invalid := func() ([]archive.Envelope, error) {
		return nil, errors.New("summary: invalid or unverified observation")
	}
	if c.Validate() != nil || !bounded(in.GeneratorVersion, 256) || !validTime(now) {
		return invalid()
	}
	x := in.Scope
	if !bounded(x.Project, 4096) || !bounded(x.Provider, 256) || !bounded(x.SourceInstance, 4096) || !bounded(x.SessionID, 4096) || x.BranchKnown != (x.Branch != "") || len(x.Branch) > 4096 || !utf8.ValidString(x.Branch) || !bounded(in.Generation, 128) || in.Cutoff < 0 {
		return invalid()
	}
	a := in.Activation
	if a == nil || a.Project != x.Project || a.Generation != in.Generation || a.Ordinal < 0 || a.Ordinal > in.Cutoff || !validTime(a.At) || now.Before(a.At) {
		return invalid()
	}
	if in.Progress != nil {
		p := in.Progress
		if p.AfterOrdinal <= a.Ordinal || p.AfterOrdinal > in.Cutoff || len(p.PreviousJobID) != 64 {
			return invalid()
		}
		if _, err := hex.DecodeString(p.PreviousJobID); err != nil {
			return invalid()
		}
	}
	if !in.ClockFloor.IsZero() && (!validTime(in.ClockFloor) || now.Before(in.ClockFloor)) {
		return invalid()
	}
	if len(in.Messages) > c.MaxObservationBytes/2 {
		return nil, errors.New("summary: observation budget exceeded; backlog")
	}
	var out []archive.Envelope
	seen := map[string]string{}
	ordinals := map[int64]string{}
	bytes := 0
	for _, e := range in.Messages {
		r := e.Record
		m := e.Metadata
		if !stringsFit(c.MaxObservationBytes-bytes, r.Project, r.Provider, r.SourceInstance, r.SessionID, r.MessageID, r.ParentID, r.Role, r.Text, string(r.Type), m.Generation) {
			return nil, errors.New("summary: observation budget exceeded; backlog")
		}
		if len(r.Role) > 256 || !utf8.ValidString(r.Role) {
			return invalid()
		}
		if m.CapturedAt != nil && (!validTime(*m.CapturedAt) || now.Before(*m.CapturedAt)) {
			return invalid()
		}

		if r.Project != x.Project || r.Provider != x.Provider || r.SourceInstance != x.SourceInstance || r.SessionID != x.SessionID || !bounded(r.MessageID, 4096) || len(r.ParentID) > 4096 || !utf8.ValidString(r.ParentID) || !utf8.ValidString(r.Text) || m.Generation != in.Generation || m.Ordinal > in.Cutoff || (r.Type != archive.TypeMessage && r.Type != archive.TypeSummary) {
			return invalid()
		}
		encoded, err := archive.EncodeEnvelope(e)
		if err != nil {
			return invalid()
		}
		if len(encoded)+1 > c.MaxObservationBytes-bytes {
			return nil, errors.New("summary: observation budget exceeded; backlog")
		}
		bytes += len(encoded) + 1
		canonical, err := archive.DecodeEnvelope(2, encoded)
		if err != nil {
			return invalid()
		}
		if r.Type == archive.TypeMessage && m.Ordinal > a.Ordinal {
			if r.Withdrawn || m.Legacy || m.CapturedAt == nil || !validTime(*m.CapturedAt) || now.Before(*m.CapturedAt) || r.ConsentEpoch <= 0 || (r.Role != "user" && r.Role != "assistant") {
				return invalid()
			}
		}
		key := archive.IdentityKey(r)
		if old, ok := seen[key]; ok {
			if old != string(encoded) {
				return nil, errors.New("summary: conflicting canonical source")
			}
			continue
		}
		if old, ok := ordinals[m.Ordinal]; ok && old != key {
			return nil, errors.New("summary: reused source ordinal")
		}
		seen[key] = string(encoded)
		ordinals[m.Ordinal] = key
		out = append(out, canonical)
	}
	sort.Slice(out, func(i, j int) bool { return out[i].Metadata.Ordinal < out[j].Metadata.Ordinal })
	return out, nil
}

func reference(e archive.Envelope) SourceRef {
	r := e.Record
	return SourceRef{Identity: Identity{r.Project, r.SourceInstance, r.SessionID, r.MessageID}, Provider: r.Provider, ParentID: r.ParentID, ConsentEpoch: r.ConsentEpoch, RecordHash: digest(r), EnvelopeHash: digest(e), Metadata: e.Metadata}
}

// String lengths are a cheap lower bound on encoded bytes. Check them before JSON
// allocation; the exact encoded-byte checks remain authoritative afterward.
func stringsFit(limit int, values ...string) bool {
	if limit < 0 {
		return false
	}
	for _, v := range values {
		if len(v) > limit {
			return false
		}
		limit -= len(v)
	}
	return true
}

func jobIdentity(m Manifest) string {
	return digest(struct {
		Progress              *Progress `json:"Progress,omitempty"`
		Scope                 Scope
		Generation, Generator string
		Config                Config
		Sources               []SourceRef
	}{m.Progress, m.Scope, m.Generation, m.GeneratorVersion, m.Config, m.Sources})
}
