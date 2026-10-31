package archive

import (
	"encoding/json"
	"errors"
)

// Each query reads a bounded raw window before privacy/search filtering. Continuations
// advance through raw records even when an entire window is withheld. Never infer a
// project-wide total from a partial window.
const ScanRecords = 1000
const ScanBytes = 8 << 20

var ErrRecordTooLarge = errors.New("archive: record exceeds query byte budget")

type Position struct {
	SessionID      string
	Seq            int
	SourceInstance string
	MessageID      string
}

func PositionOf(r Record) Position {
	return Position{r.SessionID, r.Seq, r.SourceInstance, r.MessageID}
}
func Less(a, b Position) bool {
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
}

type Window struct {
	Records []Record
	More    bool
}

func (s *MemStore) Lookup(r Record) (Record, bool, error) {
	if !s.Available() {
		return Record{}, false, ErrUnavailable
	}
	for _, v := range s.recs[r.Project] {
		if IdentityKey(v) == IdentityKey(r) {
			return v, true, nil
		}
	}
	return Record{}, false, nil
}
func (s *MemStore) Scan(project string, after *Position) (Window, error) {
	if !s.Available() {
		return Window{}, ErrUnavailable
	}
	// The fake already owns the full dataset. Production uses an indexed keyset cursor.
	hits := Query(s.recs[project], "", "")
	w := Window{}
	size := 0
	for _, h := range hits {
		r := h.Record
		if after != nil && !Less(*after, PositionOf(r)) {
			continue
		}
		b, _ := json.Marshal(r)
		if len(w.Records) == ScanRecords || size+len(b) > ScanBytes {
			if len(w.Records) == 0 {
				return Window{}, ErrRecordTooLarge
			}
			w.More = true
			break
		}
		size += len(b)
		w.Records = append(w.Records, r)
	}
	return w, nil
}
