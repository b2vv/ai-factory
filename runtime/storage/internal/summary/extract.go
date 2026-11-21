package summary

import (
	"encoding/json"
	"errors"
	"strings"
	"time"
	"unicode/utf8"
)

const ExtractorID = "local-extractive-prefix/1"
const ExtractFormat = "ai-factory.session-extract/1"
const extractNotice = "Local prefix excerpts, not a semantic summary. Original messages are the source of facts. Coverage does not prove complete native capture."

type ExtractOptions struct{ MaxExcerptBytes, MaxDocumentBytes int }

func DefaultExtractOptions() ExtractOptions { return ExtractOptions{1024, 1 << 20} }
func ExtractiveVersion(o ExtractOptions) (string, error) {
	if o.MaxExcerptBytes <= 0 || o.MaxDocumentBytes <= 0 || o.MaxDocumentBytes > 1<<20 || o.MaxExcerptBytes > o.MaxDocumentBytes {
		return "", errors.New("summary: invalid extract options")
	}
	return ExtractorID + ":" + digest(struct{ ExcerptBytes int }{o.MaxExcerptBytes}), nil
}

type Excerpt struct {
	Identity    Identity `json:"identity"`
	Role        string   `json:"role"`
	Text        string   `json:"text"`
	Start       int      `json:"start_utf8_byte"`
	End         int      `json:"end_utf8_byte"`
	SourceBytes int      `json:"source_utf8_bytes"`
	Truncated   bool     `json:"truncated"`
}
type ExtractDocument struct {
	Format       string    `json:"format"`
	Kind         string    `json:"kind"`
	Notice       string    `json:"notice"`
	JobID        string    `json:"job_id"`
	Extractor    string    `json:"extractor"`
	ExcerptBytes int       `json:"excerpt_bytes"`
	GeneratedAt  time.Time `json:"generated_at"`
	Manifest     Manifest  `json:"coverage"`
	EvidenceHash string    `json:"evidence_hash"`
	Excerpts     []Excerpt `json:"excerpts"`
}

// GenerateExtract produces literal local prefixes, never a semantic synthesis.
// Policy, durable acceptance and live-source revalidation belong to the caller.
func GenerateExtract(c Config, now time.Time, in Input, o ExtractOptions) (ExtractDocument, Decision, error) {
	version, err := ExtractiveVersion(o)
	if err != nil {
		return ExtractDocument{}, Decision{}, err
	}
	if in.GeneratorVersion != "" && in.GeneratorVersion != version {
		return ExtractDocument{}, Decision{}, errors.New("summary: incompatible extractor identity")
	}
	in.GeneratorVersion = version
	d, err := Plan(c, now, in)
	if err != nil || !d.Ready {
		return ExtractDocument{}, d, err
	}
	doc := ExtractDocument{Format: ExtractFormat, Kind: "extractive", Notice: extractNotice, JobID: d.JobID, Extractor: ExtractorID, ExcerptBytes: o.MaxExcerptBytes, GeneratedAt: now.UTC(), Manifest: d.Manifest, EvidenceHash: d.EvidenceHash, Excerpts: []Excerpt{}}
	if !headerFits(doc, o.MaxDocumentBytes) {
		return ExtractDocument{}, d, errors.New("summary: output budget exceeded")
	}
	header, err := json.Marshal(doc)
	if err != nil || len(header) > o.MaxDocumentBytes {
		return ExtractDocument{}, d, errors.New("summary: output budget exceeded")
	}
	used := len(header)
	for _, e := range d.Selected {
		r := e.Record
		end := len(r.Text)
		if end > o.MaxExcerptBytes {
			end = o.MaxExcerptBytes
		}
		for end > 0 && end < len(r.Text) && !utf8.RuneStart(r.Text[end]) {
			end--
		}

		prefix := r.Text[:end]
		if !stringsFit(o.MaxDocumentBytes-used, prefix, r.Project, r.SourceInstance, r.SessionID, r.MessageID, r.Role) {
			return ExtractDocument{}, d, errors.New("summary: output budget exceeded")
		}
		excerpt := Excerpt{Identity: Identity{r.Project, r.SourceInstance, r.SessionID, r.MessageID}, Role: r.Role, Text: prefix, End: end, SourceBytes: len(r.Text), Truncated: end < len(r.Text)}
		raw, err := json.Marshal(excerpt)
		cost := len(raw)
		if len(doc.Excerpts) > 0 {
			cost++
		}
		if err != nil || cost > o.MaxDocumentBytes-used {
			return ExtractDocument{}, d, errors.New("summary: output budget exceeded")
		}
		used += cost
		excerpt.Text = strings.Clone(prefix)
		doc.Excerpts = append(doc.Excerpts, excerpt)

	}
	return doc, d, nil
}

func headerFits(d ExtractDocument, limit int) bool {
	if len(d.Manifest.Sources) > limit/2 {
		return false
	}
	take := func(values ...string) bool {
		for _, v := range values {
			if len(v) > limit {
				return false
			}
			limit -= len(v)
		}
		return true
	}
	s := d.Manifest.Scope
	if !take(d.Format, d.Kind, d.Notice, d.JobID, d.Extractor, d.EvidenceHash, d.Manifest.Format, d.Manifest.Generation, d.Manifest.GeneratorVersion, d.Manifest.Config.Version, d.Manifest.CaptureCompleteness, s.Project, s.Provider, s.SourceInstance, s.SessionID, s.Branch) {
		return false
	}
	if d.Manifest.Progress != nil && !take(d.Manifest.Progress.PreviousJobID) {
		return false
	}
	for _, r := range d.Manifest.Sources {
		if !take(r.Identity.Project, r.Identity.SourceInstance, r.Identity.SessionID, r.Identity.MessageID, r.Provider, r.ParentID, r.RecordHash, r.EnvelopeHash, r.Metadata.Generation) {
			return false
		}
	}
	return true
}
