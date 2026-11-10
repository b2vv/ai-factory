package archive

import (
	"encoding/json"
	"errors"
	"sort"
	"unicode/utf8"
)

// SummaryQuery always names an explicit activation/source cutoff. Capture filters
// apply to original inputs only; historical head selection is factual, not serving.
type SummaryQuery struct {
	Project, Provider, Generation string
	ActivationOrdinal, Through    int64
	RevokedThrough, CaptureEpoch  int64
}
type SessionKey struct {
	SourceInstance string `bson:"source_instance"`
	SessionID      string `bson:"session_id"`
}
type SummarySource interface {
	MetadataStore
	NextSummarySession(SummaryQuery, *SessionKey) (SessionKey, bool, error)
	SummaryHead(SummaryQuery, SessionKey) (Envelope, bool, error)
	ScanSummaryOriginals(SummaryQuery, SessionKey, int64) (EnvelopeWindow, error)
	SummarySchemaReady() (bool, error)
}

var ErrSummaryQuery = errors.New("archive: invalid summary scope or cutoff")

func summaryID(v string, limit int) bool { return v != "" && len(v) <= limit && utf8.ValidString(v) }
func validSummaryQuery(q SummaryQuery) bool {
	return summaryID(q.Project, 4096) && summaryID(q.Provider, 256) && summaryID(q.Generation, 128) && q.ActivationOrdinal >= 0 && q.Through >= q.ActivationOrdinal && q.RevokedThrough >= 0 && q.CaptureEpoch >= q.RevokedThrough
}
func validSessionKey(k SessionKey) bool {
	return summaryID(k.SourceInstance, 4096) && summaryID(k.SessionID, 4096)
}
func sessionLess(a, b SessionKey) bool {
	if a.SourceInstance != b.SourceInstance {
		return a.SourceInstance < b.SourceInstance
	}
	return a.SessionID < b.SessionID
}
func matchesSummaryRange(e Envelope, q SummaryQuery) bool {
	r, m := e.Record, e.Metadata
	return r.Project == q.Project && r.Provider == q.Provider && e.Version == 2 && m.Generation == q.Generation && m.Ordinal > q.ActivationOrdinal && m.Ordinal <= q.Through
}
func eligibleSummaryOriginal(e Envelope, q SummaryQuery) bool {
	return matchesSummaryRange(e, q) && e.Record.Type == TypeMessage && !e.Record.Withdrawn && e.Record.ConsentEpoch > q.RevokedThrough && e.Record.ConsentEpoch <= q.CaptureEpoch && !e.Metadata.Legacy && e.Metadata.DerivedKind == ""
}
func (s *MemStore) SummarySchemaReady() (bool, error) {
	if !s.Available() {
		return false, ErrUnavailable
	}
	return true, nil
}
func (s *MemStore) NextSummarySession(q SummaryQuery, after *SessionKey) (SessionKey, bool, error) {
	if !validSummaryQuery(q) || (after != nil && !validSessionKey(*after)) {
		return SessionKey{}, false, ErrSummaryQuery
	}
	if !s.Available() {
		return SessionKey{}, false, ErrUnavailable
	}
	var selected SessionKey
	found := false
	for _, r := range s.recs[q.Project] {
		e, _, err := s.LookupEnvelope(r)
		if err != nil {
			return SessionKey{}, false, err
		}
		if !eligibleSummaryOriginal(e, q) {
			continue
		}
		key := SessionKey{r.SourceInstance, r.SessionID}
		if !validSessionKey(key) {
			return SessionKey{}, false, ErrSummaryQuery
		}
		if after != nil && !sessionLess(*after, key) {
			continue
		}
		if !found || sessionLess(key, selected) {
			selected = key
			found = true
		}
	}
	return selected, found, nil
}
func (s *MemStore) SummaryHead(q SummaryQuery, key SessionKey) (Envelope, bool, error) {
	if !validSummaryQuery(q) || !validSessionKey(key) {
		return Envelope{}, false, ErrSummaryQuery
	}
	if !s.Available() {
		return Envelope{}, false, ErrUnavailable
	}
	var head Envelope
	found := false
	for _, r := range s.recs[q.Project] {
		if r.SourceInstance != key.SourceInstance || r.SessionID != key.SessionID {
			continue
		}
		e, _, err := s.LookupEnvelope(r)
		if err != nil {
			return Envelope{}, false, err
		}
		if matchesSummaryRange(e, q) && r.Type == TypeSummary && e.Metadata.DerivedKind == DerivedSessionExtract && (!found || e.Metadata.Ordinal > head.Metadata.Ordinal) {
			head = e
			found = true
		}
	}
	return head, found, nil
}
func (s *MemStore) ScanSummaryOriginals(q SummaryQuery, key SessionKey, after int64) (EnvelopeWindow, error) {
	if !validSummaryQuery(q) || !validSessionKey(key) || after < q.ActivationOrdinal || after > q.Through {
		return EnvelopeWindow{}, ErrSummaryQuery
	}
	if !s.Available() {
		return EnvelopeWindow{}, ErrUnavailable
	}
	list := []Envelope{}
	for _, r := range s.recs[q.Project] {
		if r.SourceInstance != key.SourceInstance || r.SessionID != key.SessionID {
			continue
		}
		e, _, err := s.LookupEnvelope(r)
		if err != nil {
			return EnvelopeWindow{}, err
		}
		if eligibleSummaryOriginal(e, q) && e.Metadata.Ordinal > after {
			list = append(list, e)
		}
	}
	sort.Slice(list, func(i, j int) bool { return list[i].Metadata.Ordinal < list[j].Metadata.Ordinal })
	w := EnvelopeWindow{}
	size := 0
	for _, e := range list {
		raw, err := json.Marshal(e)
		if err != nil {
			return EnvelopeWindow{}, err
		}
		if len(w.Records) == EnvelopeScanRecords || len(raw) > ScanBytes-size {
			if len(w.Records) == 0 {
				return EnvelopeWindow{}, ErrRecordTooLarge
			}
			w.More = true
			break
		}
		size += len(raw)
		w.Records = append(w.Records, e)
	}
	return w, nil
}
