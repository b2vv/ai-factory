package ingest

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"

	"aifactory.local/storage/internal/archive"
	"aifactory.local/storage/internal/budget"
	"aifactory.local/storage/internal/wal"
)

func intent(kind, key string, payload []byte) budget.Evidence {
	k := sha256.Sum256([]byte(key))
	p := sha256.Sum256(payload)
	return budget.Evidence{Kind: kind, KeyHash: hex.EncodeToString(k[:]), PayloadHash: hex.EncodeToString(p[:])}
}
func (i *Ingestor) SetBudget(l *budget.Ledger) error {
	i.mu.Lock()
	defer i.mu.Unlock()
	i.budget = l
	pending := l.Snapshot().Pending
	if len(pending) == 0 {
		return nil
	}
	if len(pending) != 1 || (pending[0].Evidence.Kind != "ingest" && pending[0].Evidence.Kind != "maintenance") {
		return nil
	}
	recs, rep, e := wal.Accepted(i.dir)
	if e != nil {
		return e
	}
	if rep.IsBlocked() {
		return budget.ErrBlocked
	}
	return l.Recover(func(p budget.Intent) (bool, error) {
		if p.Evidence.Kind == "maintenance" {
			hash := recordsHash(recs, nil)
			return hash == p.Evidence.KeyHash || hash == p.Evidence.PayloadHash, nil
		}
		for _, r := range recs {
			if intent("ingest", r.Key, r.Payload) == p.Evidence {
				return true, nil
			}
		}
		return false, nil
	})
}

// PendingLogicalBytes is a read-only, size-bounded inventory independent of an
// Ingestor mutex. Callers already hold the global writer fence. Archive copies
// verified identical discharge projection debt even before checkpoint repair.
func PendingLogicalBytes(dir string, limit int64, store archive.Store) (int64, error) {
	if _, e := os.Stat(dir); os.IsNotExist(e) {
		return 0, nil
	} else if e != nil {
		return 0, e
	}
	recs, rep, e := wal.AcceptedWithin(dir, limit)
	if e != nil {
		return 0, e
	}
	if rep.IsBlocked() {
		return 0, budget.ErrBlocked
	}
	wm, e := readWatermark(filepath.Join(dir, "committed.seq"))
	if e != nil {
		return 0, e
	}
	if wm > wal.MaxSeq(recs) {
		return 0, budget.ErrBlocked
	}
	var total int64
	seen := map[string]bool{}
	for _, rc := range recs {
		if rc.Seq <= wm {
			continue
		}
		var r archive.Record
		if e = decodeWALRecord(rc, &r); e != nil {
			return 0, e
		}
		id := archive.IdentityKey(r)
		if seen[id] {
			continue
		}
		seen[id] = true
		cost := int64(64)
		if rc.Version == 2 {
			source, ok := store.(archive.MetadataStore)
			if !ok {
				return 0, ErrMetadataTransaction
			}
			expected, e := archive.DecodeEnvelope(rc.Version, rc.Payload)
			if e != nil {
				return 0, e
			}
			stored, found, e := source.LookupEnvelope(r)
			if e != nil {
				return 0, e
			}
			if found {
				a, e := archive.EncodeEnvelope(stored)
				if e != nil {
					return 0, e
				}
				b, _ := archive.EncodeEnvelope(expected)
				if string(a) != string(b) {
					return 0, fmt.Errorf("ingest: conflicting metadata inventory")
				}
			} else {
				n, e := archive.EnvelopeReservationBytes(expected)
				if e != nil {
					return 0, e
				}
				cost += n
			}
		} else {
			stored, found, e := store.Lookup(r)
			if e != nil {
				return 0, e
			}
			if found && stored != r {
				return 0, fmt.Errorf("ingest: conflicting archive inventory")
			}
			if !found {
				cost += archive.ReservationBytes(r)
			}
		}
		if total > limit || cost > limit-total {
			return 0, budget.ErrCapacity
		}
		total += cost
	}
	return total, nil
}

func recordsHash(recs []wal.Record, keep func(string, []byte) bool) string {
	h := sha256.New()
	enc := json.NewEncoder(h)
	for _, r := range recs {
		if keep == nil || keep(r.Key, r.Payload) {
			_ = enc.Encode(r)
		}
	}
	return hex.EncodeToString(h.Sum(nil))
}
func (i *Ingestor) reserveMaintenance(recs []wal.Record, keep func(string, []byte) bool, growth int64) error {
	if i.budget == nil {
		return nil
	}
	evidence := budget.Evidence{Kind: "maintenance", KeyHash: recordsHash(recs, nil), PayloadHash: recordsHash(recs, keep)}
	if len(i.budget.Snapshot().Pending) > 0 {
		return i.budget.Resume(evidence)
	}
	return i.budget.Reserve(evidence, growth)
}
