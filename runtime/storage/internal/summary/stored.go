package summary

import (
	"bytes"
	"context"
	"encoding/hex"
	"encoding/json"
	"errors"
	"io"
	"strings"
	"time"
	"unicode/utf8"

	"aifactory.local/storage/internal/archive"
)

const StoredFormat = "ai-factory.stored-session-extract/1"
const MessagePrefix = archive.SessionExtractMessagePrefix
const MaxStoredBytes = 2 << 20

var ErrInvalidStored = errors.New("summary: invalid or stale stored derivation")

// ErrVerifierClock is a temporary inability to evaluate current-time evidence.
// It must never be interpreted as permanent denial or cancel accepted WAL work.
var ErrVerifierClock = errors.New("summary: verifier clock unavailable or behind durable evidence; retry after clock recovery")

type Authority struct {
	ConsentEpoch int64
	Activation   Baseline
}
type StoredExtract struct {
	Format       string          `json:"format"`
	ConsentEpoch int64           `json:"summary_consent_epoch"`
	Activation   Baseline        `json:"activation"`
	Document     ExtractDocument `json:"document"`
}

// SealExtract verifies factual sources; it does not establish current consent.
// The writer must match Authority to control immediately before durable reserve.
func SealExtract(doc ExtractDocument, authority Authority, originals []archive.Envelope, now time.Time) (archive.Record, error) {
	if _, err := marshalDocument(doc); err != nil {
		return archive.Record{}, err
	}
	s := doc.Manifest.Scope
	r := archive.Record{Project: s.Project, Provider: s.Provider, SourceInstance: s.SourceInstance, SessionID: s.SessionID, MessageID: MessagePrefix + doc.JobID, Type: archive.TypeSummary, Role: "assistant"}
	for _, ref := range doc.Manifest.Sources {
		if r.ConsentEpoch == 0 || ref.ConsentEpoch < r.ConsentEpoch {
			r.ConsentEpoch = ref.ConsentEpoch
		}
	}
	stored := StoredExtract{StoredFormat, authority.ConsentEpoch, authority.Activation, doc}
	stored.Activation.At = stored.Activation.At.UTC()
	if !bounded(stored.Activation.Project, 4096) || !bounded(stored.Activation.Generation, 128) || !validTime(stored.Activation.At) {
		return archive.Record{}, ErrInvalidStored
	}
	raw, err := json.Marshal(stored)
	if err != nil || len(raw) > MaxStoredBytes {
		return archive.Record{}, ErrInvalidStored
	}
	r.Text = string(raw)
	parsed, err := decodeBody(r)
	if err != nil {
		return archive.Record{}, err
	}
	if err = verifyBody(parsed, originals, now); err != nil {
		return archive.Record{}, err
	}
	return r, nil
}

// DecodeStored admits only authoritative marked envelopes and bounded canonical
// data. It validates scope before a resolver may issue any covered-source lookup.
func DecodeStored(e archive.Envelope) (StoredExtract, error) {
	if len(e.Record.Text) > MaxStoredBytes || !bounded(e.Record.Project, 4096) || !bounded(e.Record.Provider, 256) || !bounded(e.Record.SourceInstance, 4096) || !bounded(e.Record.SessionID, 4096) || !bounded(e.Record.MessageID, 4096) || len(e.Record.ParentID) > 4096 || len(e.Record.Role) > 256 {
		return StoredExtract{}, ErrInvalidStored
	}
	if e.Version != 2 || e.Metadata.DerivedKind != archive.DerivedSessionExtract {
		return StoredExtract{}, ErrInvalidStored
	}
	if _, err := archive.EncodeEnvelope(e); err != nil {
		return StoredExtract{}, ErrInvalidStored
	}
	stored, err := decodeBody(e.Record)
	if err != nil {
		return StoredExtract{}, err
	}
	if e.Metadata.Generation != stored.Document.Manifest.Generation || e.Metadata.Ordinal <= stored.Document.Manifest.ObservedCutoff || e.Metadata.CapturedAt == nil || e.Metadata.CapturedAt.Before(stored.Document.GeneratedAt) {
		return StoredExtract{}, ErrInvalidStored
	}
	return stored, nil
}
func VerifyStored(e archive.Envelope, originals []archive.Envelope, now time.Time) (StoredExtract, error) {
	stored, err := DecodeStored(e)
	if err != nil {
		return StoredExtract{}, err
	}
	if !validTime(now) || now.Before(*e.Metadata.CapturedAt) {
		return StoredExtract{}, ErrVerifierClock
	}
	if err = verifyBody(stored, originals, now); err != nil {
		return StoredExtract{}, err
	}
	return stored, nil
}

func decodeBody(r archive.Record) (StoredExtract, error) {
	invalid := func() (StoredExtract, error) { return StoredExtract{}, ErrInvalidStored }
	if r.Type != archive.TypeSummary || r.Role != "assistant" || r.Seq != 0 || r.ParentID != "" || r.Edited || r.Withdrawn || len(r.Text) > MaxStoredBytes || !utf8.ValidString(r.Text) || !bounded(r.MessageID, 4096) {
		return invalid()
	}
	if err := boundedJSON(r.Text); err != nil {
		return invalid()
	}
	var stored StoredExtract
	decoder := json.NewDecoder(strings.NewReader(r.Text))
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(&stored); err != nil {
		return invalid()
	}
	if err := decoder.Decode(new(any)); err != io.EOF {
		return invalid()
	}
	doc, m, a := stored.Document, stored.Document.Manifest, stored.Activation
	s := m.Scope
	if s.BranchKnown || stored.Format != StoredFormat || stored.ConsentEpoch <= 0 || a.Project != s.Project || a.Generation != m.Generation || a.Ordinal != m.ActivationOrdinal || !validTime(a.At) || doc.GeneratedAt.Before(a.At) || s.Project != r.Project || s.Provider != r.Provider || s.SourceInstance != r.SourceInstance || s.SessionID != r.SessionID || r.MessageID != MessagePrefix+doc.JobID {
		return invalid()
	}
	if doc.Format != ExtractFormat || doc.Kind != "extractive" || doc.Extractor != ExtractorID || doc.Notice != extractNotice || m.Format != "ai-factory.summary-coverage/1" || m.CaptureCompleteness != "unknown" || m.PendingOriginals < 0 || m.PendingOriginals > m.Config.MaxObservationBytes/2 || len(m.Sources) == 0 || len(m.Sources) != len(doc.Excerpts) {
		return invalid()
	}
	version, err := ExtractiveVersion(ExtractOptions{doc.ExcerptBytes, 1 << 20})
	if err != nil || version != m.GeneratorVersion {
		return invalid()
	}
	in := Input{Scope: s, Generation: m.Generation, Cutoff: m.ObservedCutoff, Complete: true, Activation: &a, Progress: m.Progress, GeneratorVersion: m.GeneratorVersion}
	if _, err = validate(m.Config, doc.GeneratedAt, in); err != nil {
		return invalid()
	}
	after := a.Ordinal
	if m.Progress != nil {
		after = m.Progress.AfterOrdinal
	}
	minimumEpoch := int64(0)
	for _, ref := range m.Sources {
		id, meta := ref.Identity, ref.Metadata
		if id.Project != s.Project || id.SourceInstance != s.SourceInstance || id.SessionID != s.SessionID || !bounded(id.MessageID, 4096) || ref.Provider != s.Provider || len(ref.ParentID) > 4096 || !utf8.ValidString(ref.ParentID) || ref.ConsentEpoch <= 0 || meta.Generation != m.Generation || meta.Ordinal <= after || meta.Ordinal > m.ObservedCutoff || meta.Legacy || meta.DerivedKind != "" || meta.CapturedAt == nil || !validTime(*meta.CapturedAt) || doc.GeneratedAt.Before(*meta.CapturedAt) {
			return invalid()
		}
		for _, hash := range []string{ref.RecordHash, ref.EnvelopeHash} {
			if len(hash) != 64 {
				return invalid()
			}
			if _, err := hex.DecodeString(hash); err != nil {
				return invalid()
			}
		}
		if meta.SourceEventTime != nil && !validTime(*meta.SourceEventTime) {
			return invalid()
		}
		after = meta.Ordinal
		if minimumEpoch == 0 || ref.ConsentEpoch < minimumEpoch {
			minimumEpoch = ref.ConsentEpoch
		}
	}
	if r.ConsentEpoch != minimumEpoch || doc.JobID != jobIdentity(m) || doc.EvidenceHash != digest(m) {
		return invalid()
	}
	if _, err = marshalDocument(doc); err != nil {
		return invalid()
	}
	canonical, err := json.Marshal(stored)
	if err != nil || len(canonical) > MaxStoredBytes || !bytes.Equal(canonical, []byte(r.Text)) {
		return invalid()
	}
	return stored, nil
}

func verifyBody(stored StoredExtract, originals []archive.Envelope, now time.Time) error {
	d, m := stored.Document, stored.Document.Manifest
	if !validTime(now) || now.Before(d.GeneratedAt) || len(originals) != len(m.Sources) {
		return ErrInvalidStored
	}
	in := Input{Scope: m.Scope, Generation: m.Generation, Cutoff: m.ObservedCutoff, Complete: true, Activation: &stored.Activation, Progress: m.Progress, GeneratorVersion: m.GeneratorVersion, Messages: originals}
	canonical, err := validate(m.Config, d.GeneratedAt, in)
	if err != nil || len(canonical) != len(m.Sources) {
		return ErrInvalidStored
	}
	total := 0
	for i, e := range canonical {
		if e.Record.Type != archive.TypeMessage || digest(reference(e)) != digest(m.Sources[i]) {
			return ErrInvalidStored
		}
		raw, err := archive.EncodeEnvelope(e)
		if err != nil || len(raw)+1 > m.Config.MaxInputBytes-total {
			return ErrInvalidStored
		}
		total += len(raw) + 1
		end := len(e.Record.Text)
		if end > d.ExcerptBytes {
			end = d.ExcerptBytes
		}
		for end > 0 && end < len(e.Record.Text) && !utf8.RuneStart(e.Record.Text[end]) {
			end--
		}
		expected := Excerpt{Identity: Identity{e.Record.Project, e.Record.SourceInstance, e.Record.SessionID, e.Record.MessageID}, Role: e.Record.Role, Text: e.Record.Text[:end], End: end, SourceBytes: len(e.Record.Text), Truncated: end < len(e.Record.Text)}
		if expected != d.Excerpts[i] {
			return ErrInvalidStored
		}
	}
	refs, err := json.Marshal(m.Sources)
	if err != nil || len(refs) > m.Config.MaxReferenceBytes {
		return ErrInvalidStored
	}
	return nil
}

// Caller-supplied typed documents receive the same complete JSON admission as
// generation, before whole-wrapper serialization. No partial document is accepted.
func marshalDocument(doc ExtractDocument) ([]byte, error) {
	const limit = 1 << 20
	if len(doc.Excerpts) > 4096 || len(doc.Manifest.Sources) > 4096 {
		return nil, ErrInvalidStored
	}
	header := doc
	header.Excerpts = []Excerpt{}
	if !headerFits(header, limit) {
		return nil, ErrInvalidStored
	}
	raw, err := json.Marshal(header)
	if err != nil || len(raw) > limit {
		return nil, ErrInvalidStored
	}
	used := len(raw)
	for i, e := range doc.Excerpts {
		id := e.Identity
		if !stringsFit(limit-used, id.Project, id.SourceInstance, id.SessionID, id.MessageID, e.Role, e.Text) {
			return nil, ErrInvalidStored
		}
		part, err := json.Marshal(e)
		cost := len(part)
		if i > 0 {
			cost++
		}
		if err != nil || cost > limit-used {
			return nil, ErrInvalidStored
		}
		used += cost
	}
	raw, err = json.Marshal(doc)
	if err != nil || len(raw) > limit {
		return nil, ErrInvalidStored
	}
	return raw, nil
}

// Streaming shape admission bounds empty-object arrays before decoding into large
// structs. Unknown fields/duplicates are subsequently rejected by canonical bytes.
func boundedJSON(raw string) error {
	decoder := json.NewDecoder(strings.NewReader(raw))
	type frame struct {
		array bool
		count int
	}
	stack := []frame{}
	tokens := 0
	for {
		token, err := decoder.Token()
		if err == io.EOF {
			break
		}
		if err != nil {
			return ErrInvalidStored
		}
		tokens++
		if tokens > 262144 {
			return ErrInvalidStored
		}
		delimiter, isDelimiter := token.(json.Delim)
		closing := isDelimiter && (delimiter == ']' || delimiter == '}')
		if !closing && len(stack) > 0 && stack[len(stack)-1].array {
			stack[len(stack)-1].count++
			if stack[len(stack)-1].count > 4096 {
				return ErrInvalidStored
			}
		}
		if isDelimiter {
			switch delimiter {
			case '[', '{':
				stack = append(stack, frame{array: delimiter == '['})
				if len(stack) > 16 {
					return ErrInvalidStored
				}
			case ']', '}':
				if len(stack) == 0 {
					return ErrInvalidStored
				}
				stack = stack[:len(stack)-1]
			}
		}
	}
	if len(stack) != 0 {
		return ErrInvalidStored
	}
	return nil
}

// LoadStored resolves bounded covered originals only after decoding has bound all
// references to the envelope scope. Missing/changed data is an invalid proof;
// actual backend errors remain errors so callers never cancel on an outage.
// ProofReadBudget bounds starting further lookups; one already-running backend
// operation may overrun by its own timeout. Shorter caller deadlines take priority.
const ProofReadBudget = 5 * time.Second

func LoadStored(e archive.Envelope, source archive.MetadataStore, now time.Time) (StoredExtract, []archive.Envelope, error) {
	return LoadStoredContext(context.Background(), e, source, now)
}
func LoadStoredContext(ctx context.Context, e archive.Envelope, source archive.MetadataStore, now time.Time) (StoredExtract, []archive.Envelope, error) {
	if ctx == nil {
		return StoredExtract{}, nil, errors.New("summary: context required")
	}
	ctx, cancel := context.WithTimeout(ctx, ProofReadBudget)
	defer cancel()
	if err := ctx.Err(); err != nil {
		return StoredExtract{}, nil, err
	}
	stored, err := DecodeStored(e)
	if err != nil {
		return StoredExtract{}, nil, err
	}
	if source == nil {
		return StoredExtract{}, nil, archive.ErrUnavailable
	}
	originals := make([]archive.Envelope, 0, len(stored.Document.Manifest.Sources))
	for _, ref := range stored.Document.Manifest.Sources {
		if err := ctx.Err(); err != nil {
			return StoredExtract{}, nil, err
		}
		id := ref.Identity
		original, found, err := source.LookupEnvelope(archive.Record{Project: id.Project, SourceInstance: id.SourceInstance, SessionID: id.SessionID, MessageID: id.MessageID})
		if err != nil {
			return StoredExtract{}, nil, err
		}
		if err := ctx.Err(); err != nil {
			return StoredExtract{}, nil, err
		}
		if !found {
			return StoredExtract{}, nil, ErrInvalidStored
		}
		originals = append(originals, original)
	}
	if err := ctx.Err(); err != nil {
		return StoredExtract{}, nil, err
	}
	verified, err := VerifyStored(e, originals, now)
	if err != nil {
		return StoredExtract{}, nil, err
	}
	if err := ctx.Err(); err != nil {
		return StoredExtract{}, nil, err
	}
	return verified, originals, nil
}
