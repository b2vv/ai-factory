package ingest

import (
	"aifactory.local/storage/internal/archive"
	"aifactory.local/storage/internal/wal"
	"fmt"
)

// ArchivedRecord resolves legacy aliases without exposing foreign identities.
// It is a source check for derived-index proofs, not a substitute for the caller's
// final grant/consent fence. A BLOCKED WAL cannot certify a legacy source alias.
func (i *Ingestor) ArchivedRecord(key, project string) (archive.Record, bool, error) {
	i.mu.Lock()
	defer i.mu.Unlock()
	identity, ok := recordIdentity(key)
	if !ok {
		records, report, e := wal.Accepted(i.dir)
		if e != nil {
			return archive.Record{}, false, e
		}
		if report.IsBlocked() {
			return archive.Record{}, false, fmt.Errorf("ingest: blocked alias resolution")
		}
		r, _, e := i.resolveReceipt(records, key)
		if e != nil {
			return archive.Record{}, false, e
		}
		if r == nil {
			return archive.Record{}, false, nil
		}
		identity = *r
	}
	if identity.Project != project {
		return archive.Record{}, false, nil
	}
	return i.store.Lookup(identity)
}
