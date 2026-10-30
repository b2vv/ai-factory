// Package archive owns opt-in conversation captures (PLAN §3, §7, §11). The archive
// goal is ORIGINAL user-visible user/assistant messages with order/branches and
// provenance (AF1-AF3); summaries are a DISTINCT record type that never satisfy the
// archive requirement (D5). Archive queries are served by the archive store itself
// and do NOT depend on PostgreSQL (R2 / C4 / S4).
package archive

import (
	"sort"
	"strings"
)

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
type Store interface {
	Available() bool
	Put(r Record) error
	// All returns every live record for a project (serving filters applied by the
	// retention gate, not here).
	All(project string) []Record
}

// MemStore is an in-memory archive fake for the hermetic suite.
type MemStore struct {
	up   bool
	recs map[string][]Record
}

func NewMemStore() *MemStore { return &MemStore{up: true, recs: map[string][]Record{}} }

func (s *MemStore) SetAvailable(b bool) { s.up = b }
func (s *MemStore) Available() bool     { return s.up }
func (s *MemStore) Put(r Record) error {
	s.recs[r.Project] = append(s.recs[r.Project], r)
	return nil
}
func (s *MemStore) All(project string) []Record { return s.recs[project] }

// Query performs a Mongo-independent exact-substring + metadata search over a
// pre-filtered record set (the retention gate supplies the serveable set). It
// returns hits in session/seq order with provenance. Matching is literal-substring
// with case-insensitive normalization (not stemming/full-text).
func Query(records []Record, substr string, providerFilter string) []Hit {
	needle := strings.ToLower(substr)
	var hits []Hit
	for _, r := range records {
		if providerFilter != "" && r.Provider != providerFilter {
			continue
		}
		if needle != "" && !strings.Contains(strings.ToLower(r.Text), needle) {
			continue
		}
		hits = append(hits, Hit{Record: r})
	}
	sort.SliceStable(hits, func(i, j int) bool {
		if hits[i].SessionID != hits[j].SessionID {
			return hits[i].SessionID < hits[j].SessionID
		}
		return hits[i].Seq < hits[j].Seq
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
