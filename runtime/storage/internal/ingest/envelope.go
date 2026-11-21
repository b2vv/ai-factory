package ingest

import (
	"aifactory.local/storage/internal/archive"
	"aifactory.local/storage/internal/budget"
	"aifactory.local/storage/internal/config"
	"aifactory.local/storage/internal/wal"
	"bytes"
	"crypto/sha256"
	"encoding/json"
	"errors"
	"os"
	"path/filepath"
)

var ErrMetadataTransaction = errors.New("ingest: v2 source requires control-owned metadata transaction")

func decodeWALRecord(rc wal.Record, r *archive.Record) error {
	e, err := archive.DecodeEnvelope(rc.Version, rc.Payload)
	if err != nil {
		return err
	}
	*r = e.Record
	return nil
}

// AcceptEnvelope consumes an existing, exact control-owned reservation. It never
// creates or finishes a budget intent. The caller holds the control transaction.
func (i *Ingestor) AcceptEnvelope(e archive.Envelope) (wal.Receipt, error) {
	raw, err := archive.EncodeEnvelope(e)
	if err != nil {
		return wal.Receipt{}, err
	}
	key := archive.IdentityKey(e.Record)
	i.mu.Lock()
	defer i.mu.Unlock()
	if i.budget == nil {
		return wal.Receipt{}, budget.ErrBlocked
	}
	if err := i.budget.Resume(intent("archive-source-v2", key, raw)); err != nil {
		return wal.Receipt{}, err
	}
	recs, rep, err := wal.AcceptedWithin(i.dir, i.acct.WALMaintenanceLimit())
	if err != nil {
		return wal.Receipt{}, err
	}
	if rep.IsBlocked() {
		return wal.Receipt{}, budget.ErrBlocked
	}
	for _, rc := range recs {
		var r archive.Record
		if err := decodeWALRecord(rc, &r); err != nil {
			return wal.Receipt{}, err
		}
		if archive.IdentityKey(r) == key {
			if rc.Version != 2 || !bytes.Equal(rc.Payload, raw) {
				return wal.Receipt{}, wal.ErrKeyConflict
			}
			return wal.Receipt{Key: key, Seq: rc.Seq, Duplicate: true}, nil
		}
		if rc.Seq > i.committed {
			return wal.Receipt{}, ErrMetadataTransaction
		}
	}
	wb, err := i.w.Bytes()
	if err != nil {
		return wal.Receipt{}, err
	}
	cost := wal.RecordCost(key, raw)
	if wb > i.acct.WALMaintenanceLimit() || cost > i.acct.WALMaintenanceLimit()-wb {
		return wal.Receipt{}, budget.ErrCapacity
	}
	sourceCost, err := archive.EnvelopeReservationBytes(e)
	if err != nil {
		return wal.Receipt{}, err
	}
	i.reservationTotal += cost
	receipt, err := i.w.AcceptV2(key, raw)
	// Reseed even after uncertain persistence; never admit using stale physical bytes.
	if n, e := i.w.Bytes(); e != nil {
		i.acctInvalid = true
	} else {
		i.walBytes = n
		i.acctInvalid = false
	}
	// Has is established only after the accepted frame/marker are durable, even
	// when persisting the rebuildable dedup index then fails. Charge that acceptance
	// exactly once; earlier duplicate detection avoids charging its retry again.
	if i.w.Has(key) && !errors.Is(err, wal.ErrKeyConflict) && !errors.Is(err, wal.ErrVersionConflict) {
		i.acceptedTotal += cost + sourceCost
		i.pendingArchive[key] = sourceCost
		i.pendingArchiveBytes += sourceCost
		original, _ := json.Marshal(e.Record)
		i.identHash[key] = sha256.Sum256(original)
	}
	if err != nil {
		return receipt, err
	}

	return receipt, nil
}

// MarkEnvelopeProcessed follows the verified durable control commit/cancel. It
// advances only the next exact intake record and leaves ledger Finish to control.
func (i *Ingestor) MarkEnvelopeProcessed(e archive.Envelope) error {
	raw, err := archive.EncodeEnvelope(e)
	if err != nil {
		return err
	}
	key := archive.IdentityKey(e.Record)
	i.mu.Lock()
	defer i.mu.Unlock()
	if i.budget == nil {
		return budget.ErrBlocked
	}
	if err := i.budget.Resume(intent("archive-source-v2", key, raw)); err != nil {
		return err
	}
	recs, rep, err := wal.AcceptedWithin(i.dir, i.acct.WALMaintenanceLimit())
	if err != nil {
		return err
	}
	if rep.IsBlocked() {
		return budget.ErrBlocked
	}
	for _, rc := range recs {
		if rc.Key == key {
			if rc.Version != 2 || !bytes.Equal(rc.Payload, raw) {
				return wal.ErrKeyConflict
			}
			if rc.Seq <= i.committed {
				return nil
			}
			if err := writeWatermark(i.wmPath, rc.Seq); err != nil {
				return err
			}
			i.committed = rc.Seq
			if debt, ok := i.pendingArchive[key]; ok {
				i.pendingArchiveBytes -= debt
				i.reservationTotal += debt
				delete(i.pendingArchive, key)
			}
			original, _ := json.Marshal(e.Record)
			i.identHash[key] = sha256.Sum256(original)
			return nil
		}
		if rc.Seq > i.committed {
			return ErrMetadataTransaction
		}
	}
	return errors.New("ingest: reserved envelope not accepted")
}

func (i *Ingestor) verifyEnvelopeSource(rc wal.Record) (bool, error) {
	source, ok := i.store.(archive.MetadataStore)
	if !ok {
		return false, ErrMetadataTransaction
	}
	expected, err := archive.DecodeEnvelope(rc.Version, rc.Payload)
	if err != nil {
		return false, err
	}
	got, found, err := source.LookupEnvelope(expected.Record)
	if err != nil || !found {
		return found, err
	}
	raw, err := archive.EncodeEnvelope(got)
	if err != nil {
		return false, err
	}
	expectedRaw, _ := archive.EncodeEnvelope(expected)
	if !bytes.Equal(raw, expectedRaw) {
		return false, archive.ErrIDConflict
	}
	return true, nil
}

// OpenExisting is required once control contains an archive metadata witness.
// Missing intake evidence must not become a new empty journal during recovery.
func OpenExisting(dir string, acct *config.Accountant, store archive.Store) (*Ingestor, error) {
	return openIngestor(dir, acct, store, true)
}

// AcceptedEnvelope returns detached recovery evidence from an intact, clean intake
// journal. A negative result is never inferred from missing or ambiguous files.
// The caller must hold the control writer fence when using this proof to cancel.
func (i *Ingestor) AcceptedEnvelope(identity archive.Record) (archive.Envelope, bool, error) {
	i.mu.Lock()
	defer i.mu.Unlock()
	for _, name := range []string{"data", "intents", "accepts", "committed.idx"} {
		st, err := os.Lstat(filepath.Join(i.dir, name))
		if err != nil {
			return archive.Envelope{}, false, err
		}
		if !st.Mode().IsRegular() {
			return archive.Envelope{}, false, budget.ErrBlocked
		}
	}
	recs, rep, err := wal.AcceptedWithin(i.dir, i.acct.WALMaintenanceLimit())
	if err != nil {
		return archive.Envelope{}, false, err
	}
	if rep.IsBlocked() || rep.TruncateAt >= 0 {
		return archive.Envelope{}, false, budget.ErrBlocked
	}
	key := archive.IdentityKey(identity)
	for _, rc := range recs {
		e, err := archive.DecodeEnvelope(rc.Version, rc.Payload)
		if err != nil {
			return archive.Envelope{}, false, err
		}
		if archive.IdentityKey(e.Record) != key {
			continue
		}
		if rc.Version != 2 || rc.Key != key {
			return archive.Envelope{}, false, ErrMetadataTransaction
		}
		return e, true, nil
	}
	return archive.Envelope{}, false, nil
}

// KnownAcceptedIdentity is only a positive hint from the existing canonical
// receipt index. False never proves journal absence or authorizes cancellation;
// normal durable acceptance still enforces complete WAL uniqueness/integrity.
func (i *Ingestor) KnownAcceptedIdentity(r archive.Record) bool {
	i.mu.Lock()
	defer i.mu.Unlock()
	_, known := i.identHash[archive.IdentityKey(r)]
	return known
}
