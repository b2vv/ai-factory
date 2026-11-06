// Package archive owns opt-in conversation captures (PLAN §3, §7, §11). The archive
// goal is ORIGINAL user-visible user/assistant messages with order/branches and
// provenance (AF1-AF3); summaries are a DISTINCT record type that never satisfy the
// archive requirement (D5). Archive queries are served by the archive store itself
// and do NOT depend on PostgreSQL (R2 / C4 / S4).
package archive

import (
	"encoding/json"
	"sort"
	"strings"

	"golang.org/x/text/cases"
	"golang.org/x/text/unicode/norm"
)

// IdentityKey returns an UNAMBIGUOUS canonical idempotency key for a record's identity
// (project, source instance, session, message). A naive delimiter join (e.g. "a|b|c|d") is
// ambiguous — ("a|b","c","d") and ("a","b|c","d") collide — so identity is encoded as a JSON
// array, which is injective in its four components. This matches the archive's compound _id
// and is what the WAL dedups/conflicts on (see wal.ErrKeyConflict).
func IdentityKey(r Record) string {
	b, _ := json.Marshal([]string{r.Project, r.SourceInstance, r.SessionID, r.MessageID})
	return string(b)
}

// RecordType separates original history from interim summaries (D5).
type RecordType string

const (
	TypeMessage RecordType = "message" // original user-visible user/assistant message
	TypeSummary RecordType = "summary" // interim derived aid; NEVER original-history coverage
)

// Record is one archived item with provenance and the consent epoch under which it
// was collected (R3).
type Record struct {
	Project        string
	Provider       string
	SourceInstance string
	SessionID      string
	MessageID      string
	Seq            int    // per-session order
	ParentID       string // branch provenance
	Type           RecordType
	Role           string // "user" | "assistant" (for messages)
	Text           string
	Edited         bool
	Withdrawn      bool
	ConsentEpoch   int64
}

// Hit is a query result carrying provenance and source references.
type Hit struct {
	Record
}

// Store is the archive backend (MongoDB in production; faked in tests). It never
// depends on PostgreSQL.
//
// Put MUST be IDEMPOTENT by record identity (project, source instance, session, message):
//   - the same identity with the SAME content is a no-op (returns nil) - this is the
//     NECESSARY protection against redelivery (ingestion is at-least-once: a crash between
//     an archive commit and the ingest progress checkpoint causes a re-Put);
//   - the same identity with a DIFFERENT payload returns ErrIDConflict (never a silent
//     overwrite, never a false "successful replay").
//
// Every Store implementation (including MemStore) must honor this contract; it is not an
// optimization, and the ingest watermark does NOT replace it.
type Store interface {
	Available() bool
	Put(r Record) error
	// Fetch returns every live record for a project (serving filters applied by the retention
	// gate, not here). It MUST propagate a per-operation read error: a query/cursor/decode
	// failure returns a non-nil error, NEVER a silent empty slice that a caller could serve as
	// "no history". A cached availability flag is not a substitute for the actual read result.
	Fetch(project string) ([]Record, error)
	Scan(project string, after *Position) (Window, error)
	Lookup(identity Record) (Record, bool, error)
	// Purge PHYSICALLY removes records from the archive for a project (session=="" means the
	// whole project; otherwise only that session). It is the physical-erasure half of
	// deletion (PLAN §11.1 "queue compaction/erasure"), distinct from the serve-gate hide.
	// Returns the number of records removed. Non-resurrection after purge is enforced by the
	// retained deletion barrier (checked at every publish/serve/restore path), not by Purge.
	Purge(project, session string) (int, error)
}

// MemStore is an in-memory archive fake for the hermetic suite. It honors the Store Put
// idempotency contract (identity dedup + conflict), matching MongoStore, so tests exercise
// the real redelivery semantics rather than an append-only approximation.
type MemStore struct {
	metadata map[string]Metadata
	up       bool
	recs     map[string][]Record
}

func NewMemStore() *MemStore { return &MemStore{up: true, recs: map[string][]Record{}} }

func (s *MemStore) SetAvailable(b bool) { s.up = b }
func (s *MemStore) Available() bool     { return s.up }

func sameIdentity(a, b Record) bool {
	return a.Project == b.Project && a.SourceInstance == b.SourceInstance &&
		a.SessionID == b.SessionID && a.MessageID == b.MessageID
}

func (s *MemStore) Put(r Record) error {
	for _, e := range s.recs[r.Project] {
		if sameIdentity(e, r) {
			if sameContent(e, r) {
				return nil // idempotent replay
			}
			return ErrIDConflict // same identity, different payload
		}
	}
	s.recs[r.Project] = append(s.recs[r.Project], r)
	return nil
}

// All is a concrete convenience for the hermetic tests (no error). Production code paths use
// Fetch (the Store interface) so that a real backend read error is propagated.
func (s *MemStore) All(project string) []Record { return s.recs[project] }

// Fetch satisfies the Store interface. The fake has no read-fault of its own, so it returns
// the records when up and ErrUnavailable when marked down (fail closed, never empty-as-ok).
func (s *MemStore) Fetch(project string) ([]Record, error) {
	if !s.up {
		return nil, ErrUnavailable
	}
	return s.recs[project], nil
}

func (s *MemStore) Purge(project, session string) (int, error) {
	list := s.recs[project]
	if session == "" {
		n := len(list)
		for _, r := range list {
			delete(s.metadata, IdentityKey(r))
		}
		delete(s.recs, project)
		return n, nil
	}
	kept := list[:0:0]
	removed := 0
	for _, r := range list {
		if r.SessionID == session {
			delete(s.metadata, IdentityKey(r))
			removed++
			continue
		}
		kept = append(kept, r)
	}
	s.recs[project] = kept
	return removed, nil
}

// Query performs a Mongo-independent exact-substring + metadata search over a
// pre-filtered record set (the retention gate supplies the serveable set). It
// returns hits in session/seq order with provenance. Matching is literal-substring
// with NFC normalization and Unicode case folding (not stemming/full-text).
func Query(records []Record, substr string, providerFilter string) []Hit {
	needle := normalizedQueryText(substr)
	var hits []Hit
	for _, r := range records {
		if providerFilter != "" && r.Provider != providerFilter {
			continue
		}
		if needle != "" && !strings.Contains(normalizedQueryText(r.Text), needle) {
			continue
		}
		hits = append(hits, Hit{Record: r})
	}
	// TOTAL order over identity (P2-1): SessionID then per-session Seq, then the remaining
	// identity components (SourceInstance, MessageID). Seq is per-session, so two records from
	// DIFFERENT source instances can share session+seq; without the extra tie-breakers their
	// relative order would depend on input order, and offset pagination over an unchanged set
	// could duplicate one and skip another across requests. The full identity is unique, so this
	// is a stable total order independent of the store's row ordering.
	sort.Slice(hits, func(i, j int) bool {
		a, b := hits[i], hits[j]
		if a.SessionID != b.SessionID {
			return a.SessionID < b.SessionID
		}
		if a.Seq != b.Seq {
			return a.Seq < b.Seq
		}
		if a.SourceInstance != b.SourceInstance {
			return a.SourceInstance < b.SourceInstance
		}
		return a.MessageID < b.MessageID
	})
	return hits
}

// OriginalHistoryCount reports how many records are original messages (summaries are
// excluded), used to assert that summaries never count as archive completion (AF2).
func OriginalHistoryCount(records []Record) int {
	n := 0
	for _, r := range records {
		if r.Type == TypeMessage {
			n++
		}
	}
	return n
}

// Normalize only the comparison copy. Original payload and identity bytes remain
// unchanged for provenance, idempotency, checksums and deletion matching.
func normalizedQueryText(s string) string {
	return norm.NFC.String(cases.Fold().String(norm.NFC.String(s)))
}
