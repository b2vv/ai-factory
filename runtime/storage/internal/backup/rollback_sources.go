package backup

import (
	"aifactory.local/storage/internal/archive"
	"bufio"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"io"
	"time"
)

// ReadRollbackSources verifies the complete backup, retaining only bounded
// workflow metadata and archive identity/hash proofs, not archive payload copies.
func ReadRollbackSources(input io.Reader, now time.Time) (Snapshot, map[string]string, error) {
	reader := bufio.NewReader(input)
	proofs := map[string]string{}
	used := 0
	add := func(r archive.Record) error {
		key := archive.IdentityKey(r)
		raw, e := json.Marshal(r)
		if e != nil {
			return e
		}
		h := sha256.Sum256(raw)
		value := hex.EncodeToString(h[:])
		if old, ok := proofs[key]; ok {
			if old != value {
				return fmt.Errorf("backup: conflicting archive identity")
			}
			return nil
		}
		used += len(key) + len(value) + 64
		if used > MaxBytes || len(proofs) >= 100000 {
			return fmt.Errorf("backup: rollback proof bound exceeded")
		}
		proofs[key] = value
		return nil
	}
	if !isStream(reader) {
		snap, e := ReadSnapshot(reader, now)
		if e != nil {
			return snap, nil, e
		}
		for _, p := range snap.Projects {
			for _, r := range p.Archive {
				if e = add(r); e != nil {
					return snap, nil, e
				}
			}
		}
		return snap, proofs, nil
	}
	snap := Snapshot{Version: 2}
	created, e := walkStream(reader, now, false, func(f streamFrame) error {
		if f.Kind == "project" {
			raw, e := json.Marshal(f.Project)
			if e != nil {
				return e
			}
			used += len(raw)
			if used > MaxBytes {
				return fmt.Errorf("backup: rollback metadata bound exceeded")
			}
			snap.Projects = append(snap.Projects, *f.Project)
		}
		if f.Kind == "record" {
			return add(*f.Record)
		}
		return nil
	})
	snap.Created = created
	return snap, proofs, e
}
