// Package ingest connects conversation capture to durable storage (PLAN §6). It REUSES the
// existing WAL durability primitive (internal/wal) as the ingestion journal and the
// existing archive store; it does NOT implement a second/parallel WAL.
//
// Record lifecycle (PLAN §6, F10): pending -> durable-accepted -> archive-committed.
//   - Accept: capacity admission (D4 caps/backpressure, config.Accountant) runs FIRST; only
//     an admitted record is written to the WAL and fsync-durable BEFORE any archive (DB)
//     commit. At the cap, intake returns backpressure and accepted records are NEVER evicted.
//   - Drain: durable-accepted records are committed to the archive (Mongo = required
//     terminal). If the archive is UNAVAILABLE, accepted records remain in the bounded WAL
//     and drain on recovery; PG is never promoted to archive authority.
//   - Recovery is fail-closed: an ambiguous/corrupt WAL is preserved + BLOCKED (never
//     truncated, never permissively reset) per the V3-1 rule.
//
// Delivery guarantee: AT-LEAST-ONCE delivery with IDEMPOTENT STORAGE. The WAL and the
// archive keep separate durable state, so no single checkpoint makes archive commit and
// progress-marking one atomic step: a crash after an archive commit but before the progress
// watermark is persisted causes a re-commit on restart. Redelivery safety therefore depends
// on the archive store's identity idempotency (archive.Store.Put is a no-op for an
// identical record and ErrIDConflict for a different payload under the same identity) - NOT
// on the watermark. The committed-watermark is only a PROGRESS CHECKPOINT that avoids
// redundant re-commits; it is written AFTER the archive commit (so it never runs ahead of a
// durable commit and cannot cause loss) and is CRC-protected (corruption is detected and
// fails closed, never silently skipping records). A stronger (exactly-once) guarantee would
// require a proven cross-store commit protocol, which this pilot does NOT build. WAL
// exact-key dedup additionally collapses an identical redelivered key before acceptance.
// Project isolation: records carry their project and the archive partitions by project.
package ingest

import (
	"crypto/sha256"
	"encoding/binary"
	"encoding/json"
	"errors"
	"fmt"
	"hash/crc32"
	"os"
	"path/filepath"
	"sync"

	"aifactory.local/storage/internal/archive"
	"aifactory.local/storage/internal/budget"
	"aifactory.local/storage/internal/config"
	"aifactory.local/storage/internal/wal"
)

// Ingestor is the durable intake + drain path for one node.
type Ingestor struct {
	budget    *budget.Ledger
	mu        sync.Mutex
	w         *wal.WAL
	dir       string
	acct      *config.Accountant
	store     archive.Store
	committed uint64 // highest processed WAL seq (includes quarantine; durable checkpoint)
	wmPath    string
	walBytes  int64 // authoritative in-memory WAL byte total (guarded by mu); the hard physical cap
	// acceptedTotal is the monotonic running sum of durable accept costs (never decreases); used
	// to reserve cross-request/in-batch in-flight bytes against stale pre-lock measurements (V3-1).
	acceptedTotal       int64
	reservationTotal    int64
	pendingArchive      map[string]int64
	pendingArchiveBytes int64
	hasReclaimed        bool
	reclaimScan         *wal.Scanner
	reclaimAfter        uint64
	// acctInvalid is set when the physical WAL size could not be re-measured after a durable
	// change error; while true, admission fails closed until a reseed succeeds (V3-2).
	acctInvalid bool
	// identHash maps a record's CANONICAL archive identity (archive.IdentityKey, decoded from
	// the payload - independent of whatever opaque WAL key string a record was stored under) to
	// sha256(payload). It is seeded from the journal on Open by DECODING payloads, so a record
	// written under a legacy/alternate key encoding is still reconciled: a later capture of the
	// same identity with different content is rejected PRE-ADMISSION (V2-3 / R2), instead of
	// being admitted and then poisoning the drain with an archive identity conflict.
	identHash map[string][32]byte
}

// rebuildIdentIndex (re)builds identHash from the current clean WAL journal by decoding each
// accepted payload. Unparseable payloads are skipped (synthetic edge). Caller holds i.mu or is
// in Open before concurrency.
func (i *Ingestor) rebuildIdentIndex() error {
	recs, rep, err := wal.Accepted(i.dir)
	if err != nil {
		return err
	}
	if rep.IsBlocked() {
		// A blocked journal is handled elsewhere (drain/compact refuse); leave the index empty.
		i.identHash = map[string][32]byte{}
		return nil
	}
	idx := make(map[string][32]byte, len(recs))
	pending := map[string]int64{}
	var pendingBytes int64
	for _, rc := range recs {
		var r archive.Record
		if err := decodeWALRecord(rc, &r); err != nil {
			if rc.Version != 1 {
				return err
			}
			continue
		}
		ident := archive.IdentityKey(r)
		original, _ := json.Marshal(r)
		idx[ident] = sha256.Sum256(original)
		if rc.Seq > i.committed {
			if _, exists := pending[ident]; !exists {
				cost := archive.ReservationBytes(r)
				if rc.Version == 2 {
					e, err := archive.DecodeEnvelope(rc.Version, rc.Payload)
					if err != nil {
						return err
					}
					cost, err = archive.EnvelopeReservationBytes(e)
					if err != nil {
						return err
					}
				}
				pending[ident] = cost
				pendingBytes += cost
			}
		}
	}
	i.identHash = idx
	i.pendingArchive = pending
	i.pendingArchiveBytes = pendingBytes
	return nil
}

// Open opens (or recovers) the ingestion WAL rooted at dir and binds the capacity
// accountant and archive store. It reuses wal.Open (the existing durability primitive) and
// loads the durable archive-committed watermark, so Drain commits each record exactly once
// regardless of whether the archive store itself deduplicates.
func Open(dir string, acct *config.Accountant, store archive.Store) (*Ingestor, error) {
	return openIngestor(dir, acct, store, false)
}
func openIngestor(dir string, acct *config.Accountant, store archive.Store, existing bool) (*Ingestor, error) {
	var w *wal.WAL
	var err error
	if existing {
		w, err = wal.OpenExisting(dir)
	} else {
		w, err = wal.Open(dir)
	}
	if err != nil {
		return nil, err
	}
	i := &Ingestor{w: w, dir: dir, acct: acct, store: store, wmPath: filepath.Join(dir, "committed.seq")}
	wm, err := readWatermark(i.wmPath)
	if err != nil {
		w.Close()
		return nil, err
	}
	i.committed = wm
	if b, e := os.ReadFile(filepath.Join(dir, "reclaimed")); e == nil {
		if string(b) != "v1\n" {
			w.Close()
			return nil, errors.New("ingest: invalid reclamation marker")
		}
		i.hasReclaimed = true
	} else if !os.IsNotExist(e) {
		w.Close()
		return nil, e
	}
	// Seed the authoritative in-memory WAL-byte counter from the actual journal size so the
	// physical cap is enforced exactly and survives restart.
	wb, err := w.Bytes()
	if err != nil {
		w.Close()
		return nil, err
	}
	i.walBytes = wb
	// Seed the canonical-identity conflict index from the journal (reconciles legacy keys).
	if err := i.rebuildIdentIndex(); err != nil {
		w.Close()
		return nil, err
	}
	return i, nil
}

// Close releases the WAL files.
func (i *Ingestor) Close() error { return i.w.Close() }

// AcceptedBytes returns the monotonic running total of durable WAL bytes this ingestor has
// accepted (never decreasing). A caller snapshots it BEFORE measuring usage; the growth since
// that snapshot is the amount OTHER requests (and earlier records of the same batch) have
// reserved but which the snapshot's measurement does not yet reflect — so the caller can
// reserve it against the shared live/free budget and two concurrently-measured requests cannot
// both spend the same one-record headroom (V3-1).
func (i *Ingestor) AcceptedBytes() int64 {
	i.mu.Lock()
	defer i.mu.Unlock()
	return i.acceptedTotal
}

// RecordCost reports WAL plus explicit archive/index representation reservations, so a batch producer can
// reserve each record's cost against the shared live/free budget across the batch (the WAL
// dimension is reserved exactly inside Accept). Returns 0 for a record whose JSON cannot be
// marshalled (it would be rejected on Accept anyway).
func RecordCost(r archive.Record) int64 {
	b, err := json.Marshal(r)
	if err != nil {
		return 0
	}
	return wal.RecordCost(archive.IdentityKey(r), b) + archive.ReservationBytes(r)
}

// Accept admits and durably accepts one record. Admission (D4 caps/backpressure) runs
// BEFORE the durable write; a rejected admission returns a backpressure/unavailable error
// and writes nothing (accepted data is never evicted to make room). The durable WAL accept
// precedes any archive commit. A repeated idempotency key is a durable no-op (F7).
func (i *Ingestor) Accept(key string, r archive.Record, usage config.Usage) (wal.Receipt, error) {
	if key == "" {
		return wal.Receipt{}, errors.New("ingest: empty idempotency key")
	}
	payload, err := json.Marshal(r)
	if err != nil {
		return wal.Receipt{}, err
	}
	i.mu.Lock()
	defer i.mu.Unlock()
	// V3-2: if a prior Accept left the physical WAL size UNKNOWN (a durable/partial change whose
	// size could not be re-measured), accounting is invalid. Retry the reseed; if it still fails,
	// FAIL CLOSED (refuse admission) rather than admit against a stale counter that could bypass
	// the physical cap. A recovered reseed clears the state and resumes.
	if i.acctInvalid {
		if wb, be := i.w.Bytes(); be == nil {
			i.walBytes = wb
			i.acctInvalid = false
		} else {
			return wal.Receipt{}, fmt.Errorf("ingest: WAL size unknown after a prior durable-change error; admission refused (fail-closed) until accounting is re-established: %w", be)
		}
	}
	// Canonical-identity check (R2 / V2-3 / V3-3), PRE-ADMISSION and independent of the opaque
	// WAL key string (legacy delimiter vs new JSON). Decoded-payload identity reconciles prior
	// records written under any key encoding:
	//   - same identity, DIFFERENT payload  -> conflict (409), kept out of the WAL entirely;
	//   - same identity, IDENTICAL payload   -> benign duplicate NO-OP, returned BEFORE capacity
	//     admission and WITHOUT a new frame (so a legacy-key byte-identical replay neither
	//     appends a second frame nor is rejected by backpressure at a full WAL).
	ident := archive.IdentityKey(r)
	ph := sha256.Sum256(payload)
	if stored, ok := i.identHash[ident]; ok {
		if stored != ph {
			return wal.Receipt{}, wal.ErrKeyConflict
		}
		return wal.Receipt{Key: key, Duplicate: true}, nil
	}
	// Reclaimed identities remain authoritative in the archive. Lookup errors are
	// not absence: fail closed before accepting a potentially conflicting replay.
	if i.hasReclaimed {
		if stored, found, e := i.store.Lookup(r); e != nil {
			return wal.Receipt{}, e
		} else if found {
			if stored != r {
				return wal.Receipt{}, wal.ErrKeyConflict
			}
			return wal.Receipt{Key: key, Duplicate: true}, nil
		}
	}
	// Admission is ATOMIC with the durable write (R3): the FULL persistent cost (frame + key +
	// reservation + accept marker + dedup index, not just the JSON payload) is reserved against
	// the authoritative in-memory WAL counter, under the same lock that serializes the write.
	// This enforces the physical WAL cap exactly and prevents two concurrent requests from
	// admitting against the same remaining capacity. A benign replay (key already present)
	// writes nothing, so it is charged 0 and never rejected at the cap. The meter-supplied
	// live/free figures are kept; only WALBytes is overridden with the exact in-memory total.
	// keyIsNew captures, BEFORE the write, whether this opaque key is absent from the WAL. It
	// gates both the cost (a benign replay of an existing key writes nothing) and the error-path
	// durable accounting below: only a key that did NOT exist before this call can have been
	// newly durably accepted BY this call (a pre-existing key that errors is a conflict or a
	// no-op touching an OTHER record, never a new acceptance of the current payload).
	keyIsNew := !i.w.Has(key)
	cost := int64(0)
	if keyIsNew {
		cost = wal.RecordCost(key, payload)
	}
	eff := usage
	eff.WALBytes = i.walBytes
	eff.LiveBytes += i.pendingArchiveBytes
	eff.FreeBytes -= i.pendingArchiveBytes
	if eff.FreeBytes < 0 {
		eff.FreeBytes = 0
	}
	liveCost := cost
	archiveCost := int64(0)
	if keyIsNew {
		archiveCost = archive.ReservationBytes(r)
		liveCost += archiveCost
	}
	if adm := i.acct.AdmitGrowth(eff, cost, liveCost); !adm.Allowed {
		return wal.Receipt{}, fmt.Errorf("ingest: %s", adm.Reason)
	}
	// Charge every admitted write attempt, including partial-error paths, to
	// stale concurrent measurements. Pending archive debt exists only after acceptance.
	if i.budget != nil && keyIsNew {
		if e := i.budget.Reserve(intent("ingest", key, payload), liveCost+64); e != nil {
			return wal.Receipt{}, e
		}
	}
	i.reservationTotal += cost
	rcpt, err := i.w.Accept(key, payload)
	if err != nil {
		// V2-2/V3-2: a record may be partially or (on a committed.idx failure) FULLY durable even
		// when Accept returns an error, and the WAL may remain appendable. Reseed the physical
		// counter from the ACTUAL journal size so it can never under-count and let a later accept
		// bypass the physical cap. If the reseed ITSELF fails (the physical size is now UNKNOWN),
		// mark accounting invalid so the NEXT admission fails closed instead of trusting a stale
		// counter. The original error is always returned (the reseed never hides it).
		if wb, be := i.w.Bytes(); be == nil {
			i.walBytes = wb
		} else {
			i.acctInvalid = true
		}
		// V3-1 (Codex v4): the FULL durable case is a committed.idx-persist failure AFTER the
		// frame+accept marker are fsync'd. The record IS durably accepted (the WAL's authoritative
		// dedup is set) and WILL replay and drain to the archive, so it consumes live/free just
		// like a clean accept. Its reservation MUST therefore grow the monotonic cross-request
		// total EVEN on this error path: otherwise a concurrent request that sampled AcceptedBytes()
		// before us computes delta=0 and re-spends the same live/free budget (two durable records
		// admitted against a one-record budget). Record the identity too, so a later retry is a
		// benign no-op (no double-charge).
		//
		// P2 (Codex v5): Has(key) ALONE does not prove the CURRENT payload was just accepted — it
		// is also true for a PRE-EXISTING record. A same-key/different-identity CONFLICT returns
		// ErrKeyConflict with Has(key)=true but accepts NOTHING; seeding identHash for that rejected
		// payload would poison the cache and let a later canonical retry falsely succeed as a
		// duplicate with NO durable record. Account ONLY a genuinely new durable acceptance: the key
		// was absent before this call (keyIsNew) AND is present now (Has) AND the error is not a
		// conflict. A steps-1..3 failure leaves dedup UNSET (Has false) = not accepted; a conflict or
		// a pre-existing key is excluded by keyIsNew.
		if keyIsNew && i.w.Has(key) && !errors.Is(err, wal.ErrKeyConflict) {
			i.acceptedTotal += liveCost
			i.pendingArchive[ident] = archiveCost
			i.pendingArchiveBytes += archiveCost
			i.identHash[ident] = ph
		}
		return rcpt, err
	}
	// Only a genuinely new frame adds bytes; a duplicate is a no-op (cost already 0).
	if !rcpt.Duplicate {
		i.acceptedTotal += liveCost
		i.pendingArchive[ident] = archiveCost
		i.pendingArchiveBytes += archiveCost
		i.walBytes += cost
		i.identHash[ident] = ph
	}
	if i.budget != nil && keyIsNew {
		if e := i.budget.Finish(); e != nil {
			return rcpt, e
		}
	}
	return rcpt, nil
}

// Drain commits durable-accepted records to the archive (archive-committed). It is
// fail-closed: if the archive is unavailable it commits nothing and returns
// archive.ErrUnavailable (records remain durable in the WAL and drain on recovery); if WAL
// recovery is BLOCKED (ambiguous/corrupt) it commits nothing and returns an error. Commit is
// idempotent, so a partially-drained batch re-commits safely. Returns the number committed.
func (i *Ingestor) Drain() (int, error) { return i.DrainGated(nil) }

// DrainGated commits durable-accepted records to the archive, but ONLY publishes a record
// for which gate(record) is true. A record that fails the gate is QUARANTINED: it is NOT
// published to the archive (PLAN §11.1 - pre-revocation/pre-deletion items are
// paused/quarantined, NOT published), and the checkpoint advances past it so later records
// still drain. The gate MUST be monotone (a denial is permanent - consent RevokedThrough and
// deletion barriers never un-revoke), so advancing past a quarantined record is safe. A nil
// gate publishes everything (used by the pure-ingest tests with no consent context).
//
// Quarantine accounting (why a skipped record is never "lost"): the checkpoint only governs
// which records Drain RE-EXAMINES; it does not govern what the WAL CONTAINS. A quarantined
// record stays a fully durable, accepted WAL frame. wal.Accepted scans the whole validated
// journal independently of the watermark, so after the checkpoint advances past it the record
// is still enumerable, still counted by AcceptedCount, and still visible to Compact (physical
// erasure). After a restart the ingestor reopens the same journal and re-derives the identical
// accepted set; the watermark is reloaded (CRC-checked) and a quarantined record below it is
// simply not re-published, not forgotten. Manageability therefore never depends on the
// watermark: the record is addressable for erasure until Compact physically drops it.
//
// NOTE: quarantine means "not published"; it does NOT by itself physically erase the
// quarantined record from the WAL. Physical erasure is the SEPARATE Compact operation
// (invoked by project purge), which finds the record via the full-journal scan above.
func (i *Ingestor) DrainGated(gate func(archive.Record) bool) (int, error) {
	if !i.store.Available() {
		return 0, archive.ErrUnavailable
	}
	// Read the journal UNDER the lock: Compact holds i.mu for its whole close/flip/reopen, so
	// taking the lock first means a drain never observes the journal mid-rename (no transient
	// BLOCKED/unreadable race against an in-process compaction).
	i.mu.Lock()
	defer i.mu.Unlock()
	recs, rep, err := wal.Accepted(i.dir)
	if err != nil {
		return 0, err
	}
	if rep.IsBlocked() {
		return 0, fmt.Errorf("ingest: WAL recovery BLOCKED (%d region(s) preserved); fail-closed, no commit", len(rep.BlockedDx))
	}
	// Defense in depth: the progress watermark must never run ahead of the durable WAL. If
	// it does, the checkpoint is corrupt/inconsistent - fail closed rather than skip records.
	if i.committed > wal.MaxSeq(recs) {
		return 0, fmt.Errorf("ingest: committed watermark %d exceeds max durable WAL seq %d (corrupt checkpoint); fail-closed", i.committed, wal.MaxSeq(recs))
	}
	n := 0
	for _, rec := range recs {
		if rec.Seq <= i.committed {
			continue // already handled (progress checkpoint skip; store idempotency is the real redelivery guard)
		}
		if rec.Version != 1 {
			return n, ErrMetadataTransaction
		}
		var r archive.Record
		if err := decodeWALRecord(rec, &r); err != nil {
			return n, fmt.Errorf("ingest: corrupt WAL payload at seq %d: %w", rec.Seq, err)
		}
		publish := gate == nil || gate(r)
		if i.budget != nil {
			evidence := intent("archive", rec.Key, rec.Payload)
			var e error
			if len(i.budget.Snapshot().Pending) > 0 {
				e = i.budget.Resume(evidence)
			} else {
				e = i.budget.Reserve(evidence, 0)
			}
			if e != nil {
				return n, e
			}
		}
		if publish {
			if err := i.store.Put(r); err != nil {
				// archive.ErrIDConflict (same id, different payload) and backend errors both
				// surface here rather than being swallowed; the record stays durable in the WAL.
				return n, fmt.Errorf("ingest: archive commit failed at seq %d: %w", rec.Seq, err)
			}
		}
		// Advance the durable watermark AFTER the archive commit (or after a terminal
		// quarantine decision), so a crash cannot mark a record committed before it is in the
		// archive (at worst one record re-commits, which the archive's identity dedup makes a
		// no-op). A quarantined record is never published.
		if err := writeWatermark(i.wmPath, rec.Seq); err != nil {
			return n, fmt.Errorf("ingest: handled seq %d but watermark update failed: %w", rec.Seq, err)
		}
		i.committed = rec.Seq
		ident := archive.IdentityKey(r)
		if debt, ok := i.pendingArchive[ident]; ok {
			if publish {
				i.reservationTotal += debt
			} // cover a projection after another request measured
			i.pendingArchiveBytes -= debt
			delete(i.pendingArchive, ident)
		}
		if i.budget != nil {
			if e := i.budget.Finish(); e != nil {
				return n, e
			}
		}
		if publish {
			n++
		}
	}
	return n, nil
}

type watermarkFile struct {
	Committed uint64 `json:"committed"`
	CRC       uint32 `json:"crc"` // crc32 over Committed; detects silent corruption
}

func watermarkCRC(seq uint64) uint32 {
	var buf [8]byte
	binary.BigEndian.PutUint64(buf[:], seq)
	return crc32.ChecksumIEEE(buf[:])
}

// readWatermark loads the durable archive-committed high-water seq (0 if absent). A present
// but CRC-invalid watermark is CORRUPTION and fails closed (returns an error) rather than
// being trusted - so a tampered/garbled checkpoint can never silently skip uncommitted
// records.
func readWatermark(path string) (uint64, error) {
	b, err := os.ReadFile(path)
	if os.IsNotExist(err) {
		return 0, nil
	}
	if err != nil {
		return 0, err
	}
	var v watermarkFile
	if err := json.Unmarshal(b, &v); err != nil {
		return 0, fmt.Errorf("ingest: corrupt committed watermark (unparseable); fail-closed: %w", err)
	}
	if v.CRC != watermarkCRC(v.Committed) {
		return 0, fmt.Errorf("ingest: committed watermark CRC mismatch (corruption); fail-closed")
	}
	return v.Committed, nil
}

// writeWatermark persists the committed high-water atomically (temp + fsync + rename + dir
// fsync), mirroring the control registry's durable-marker discipline. It is a package var so
// a test can inject a write/crash fault between an archive commit and the checkpoint.
var writeWatermark = func(path string, seq uint64) error {
	b, _ := json.Marshal(watermarkFile{Committed: seq, CRC: watermarkCRC(seq)})
	tmp := path + ".tmp"
	f, err := os.OpenFile(tmp, os.O_CREATE|os.O_TRUNC|os.O_WRONLY, 0o600)
	if err != nil {
		return err
	}
	if _, err := f.Write(b); err != nil {
		f.Close()
		return err
	}
	if err := f.Sync(); err != nil {
		f.Close()
		return err
	}
	if err := f.Close(); err != nil {
		return err
	}
	if err := os.Rename(tmp, path); err != nil {
		return err
	}
	d, err := os.Open(filepath.Dir(path))
	if err != nil {
		return err
	}
	defer d.Close()
	return d.Sync()
}

// CompactOutcome reports the result of a WAL compaction.
type CompactOutcome struct {
	Dropped int // records physically removed from the WAL journal
	// ResidualUnparseable counts frames that could NOT be classified (payload did not
	// unmarshal) and were therefore KEPT rather than risk erasing an unrelated project. When
	// this is >0 the caller MUST NOT claim complete erasure of the target: a frame that might
	// belong to the target project physically remains in the journal.
	ResidualUnparseable int
}

// Compact PHYSICALLY removes WAL records for which keep(record) is false (a purged /
// deletion-barred project) from the MANAGED intake journal, preserving every other record,
// crash-safe (wal.Compact's staged-generation + commit-sentinel flip). It is the WAL half of
// managed-store deletion: the archive Purge removes the archive copy, Compact removes the
// intake-journal bytes, so a later re-drain cannot re-materialize the dropped payload.
//
// SCOPE OF "removal": this erases the record from the MANAGED stores (archive + WAL journal)
// only. It does NOT and cannot guarantee destruction of every physical copy on the underlying
// media (filesystem free-list remnants, snapshots, backups, replica media) - that is out of
// this layer's control. Callers must not report it as irreversible media-level erasure.
//
// Fail-closed: refuses when WAL recovery is BLOCKED (ambiguous tails are preserved, never
// deleted). A frame whose payload cannot be classified is KEPT (never silently erased on
// ambiguity) and counted in ResidualUnparseable so the caller can avoid a false
// complete-erasure claim. After compaction it clamps the durable watermark down to the new
// max sequence. Non-resurrection of a dropped record is enforced by the RETAINED deletion
// barrier (its key is intentionally gone from the rebuilt dedup index); the caller MUST set
// the barrier first, and the barrier is NOT removed by Compact.
func (i *Ingestor) Compact(keep func(archive.Record) bool) (CompactOutcome, error) {
	i.mu.Lock()
	defer i.mu.Unlock()
	return i.compactLocked(keep)
}

// compactLocked holds the same reservation fence through checkpoint and flip.
func (i *Ingestor) compactLocked(keep func(archive.Record) bool) (CompactOutcome, error) {
	return i.compactPeakLocked(keep, i.acct.WALMaintenanceLimit())
}

// CompactWithUsage is operator-triggered erasure, with live/free staging and
// pending projection liabilities reserved under the same ingest mutex.
func (i *Ingestor) CompactWithUsage(keep func(archive.Record) bool, usage config.Usage) (CompactOutcome, error) {
	i.mu.Lock()
	defer i.mu.Unlock()
	current, e := wal.ManagedBytes(i.dir)
	if e != nil {
		return CompactOutcome{}, e
	}
	peak, e := i.acct.MaintenancePeakWithPending(usage, current, i.pendingArchiveBytes)
	if e != nil {
		return CompactOutcome{}, fmt.Errorf("%w: %v", wal.ErrMaintenanceBudget, e)
	}
	return i.compactPeakLocked(keep, peak)
}
func (i *Ingestor) compactPeakLocked(keep func(archive.Record) bool, peak int64) (CompactOutcome, error) {
	// Refuse on a blocked journal before touching anything (defense in depth; wal.Compact
	// also refuses, but we must not even close/reopen around a blocked log).
	recs0, rep, err := wal.AcceptedWithin(i.dir, i.acct.WALMaintenanceLimit())
	if err != nil {
		return CompactOutcome{}, err
	}
	if rep.IsBlocked() {
		return CompactOutcome{}, fmt.Errorf("ingest: WAL recovery BLOCKED (%d region(s)); refusing to compact, fail-closed", len(rep.BlockedDx))
	}
	// R4: make the checkpoint and the compaction one recoverable transition. Compute the max
	// sequence that will REMAIN after compaction (unclassifiable frames are kept, so they
	// count), then clamp the durable watermark DOWN to it BEFORE the journal flip. Lowering the
	// watermark is always safe (it never skips an uncommitted record: every retained record has
	// seq<=retainedMax, and a record already committed stays committed). Because the clamp is
	// persisted first and the flip is itself atomic (sentinel), a crash at ANY boundary leaves a
	// consistent pair: old journal + clamped(<=oldMax) watermark, or new journal + watermark
	// equal to its max. The old post-flip clamp left a window where committed>MaxSeq was
	// misread as corruption; clamping first removes that window without any arbitrary clamp and
	// without weakening preserve+BLOCK.
	// Pre-flip corruption guard: a healthy checkpoint never exceeds the current durable journal.
	// If it already does on entry, that is pre-existing watermark corruption (NOT a compaction
	// artifact) - fail closed rather than let the clamp below silently mask it.
	if oldMax := wal.MaxSeq(recs0); i.committed > oldMax {
		return CompactOutcome{}, fmt.Errorf("ingest: committed watermark %d exceeds max durable WAL seq %d before compaction (corrupt checkpoint); refusing to compact, fail-closed", i.committed, oldMax)
	}
	residualUnparseable := 0
	var retainedMax uint64
	for _, rc := range recs0 {
		keepIt := true
		var r archive.Record
		if decodeWALRecord(rc, &r) == nil {
			keepIt = keep(r)
		} else {
			residualUnparseable++
		}
		if keepIt && rc.Seq > retainedMax {
			retainedMax = rc.Seq
		}
	}
	// Reserve old+new generation and checkpoint/sentinel bytes before changing
	// the watermark or closing the live WAL. No extra scratch allowance is hidden.
	budget := wal.MaintenanceBudget{MaxInputBytes: i.acct.WALMaintenanceLimit(), MaxPeakBytes: peak}
	formats := map[string]uint8{}
	for _, rc := range recs0 {
		formats[rc.Key] = rc.Version
	}
	keepRaw := func(key string, payload []byte) bool {
		var r archive.Record
		if decodeWALRecord(wal.Record{Key: key, Payload: payload, Version: formats[key]}, &r) != nil {
			return true
		}
		return keep(r)
	}
	checkpoint, _ := json.Marshal(watermarkFile{Committed: retainedMax, CRC: watermarkCRC(retainedMax)})
	plan, err := wal.PlanCompaction(i.dir, recs0, keepRaw, budget, int64(len(checkpoint)))
	if err != nil {
		return CompactOutcome{}, err
	}
	if e := i.reserveMaintenance(recs0, keepRaw, plan.PeakBytes-plan.InputBytes); e != nil {
		return CompactOutcome{}, e
	}
	if i.committed > retainedMax {
		if err := writeWatermark(i.wmPath, retainedMax); err != nil {
			return CompactOutcome{}, fmt.Errorf("ingest: pre-compaction watermark clamp failed: %w", err)
		}
		i.committed = retainedMax
	}
	// wal.Compact operates on the directory with the journal CLOSED; close and reopen around it.
	if err := i.w.Close(); err != nil {
		return CompactOutcome{}, err
	}
	res, cerr := wal.CompactWithin(i.dir, keepRaw, budget)
	w, oerr := wal.OpenExisting(i.dir)
	if oerr != nil {
		return CompactOutcome{}, fmt.Errorf("ingest: reopen after compaction failed: %w", oerr)
	}
	i.w = w
	// Reseed the WAL-byte counter from the now-smaller journal (compaction freed bytes).
	if wb, berr := w.Bytes(); berr == nil {
		i.walBytes = wb
		i.acctInvalid = false
	} else {
		i.acctInvalid = true
		return CompactOutcome{}, fmt.Errorf("ingest: physical accounting after compaction unavailable: %w", berr)
	}
	// Reseed the canonical-identity index so dropped identities are no longer tracked.
	if rerr := i.rebuildIdentIndex(); rerr != nil {
		return CompactOutcome{}, rerr
	}
	if cerr != nil {
		return CompactOutcome{}, cerr
	}
	// The watermark was already clamped (above) before the flip, so after a successful reopen it
	// is guaranteed <= the new MaxSeq. Cross-check defensively and fail closed on any surprise.
	recs, _, aerr := wal.Accepted(i.dir)
	if aerr != nil {
		return CompactOutcome{}, aerr
	}
	if maxSeq := wal.MaxSeq(recs); i.committed > maxSeq {
		return CompactOutcome{}, fmt.Errorf("ingest: post-compaction invariant broken (committed %d > maxSeq %d)", i.committed, maxSeq)
	}
	if i.budget != nil {
		if e := i.budget.Finish(); e != nil {
			return CompactOutcome{}, e
		}
	}
	return CompactOutcome{Dropped: res.Dropped, ResidualUnparseable: residualUnparseable}, nil
}

// AcceptedCount reports how many records are durable-accepted in the WAL (for tests/metrics).
// It reads under the lock so it never observes the journal mid-compaction-flip.
func (i *Ingestor) AcceptedCount() (int, error) {
	i.mu.Lock()
	defer i.mu.Unlock()
	recs, rep, err := wal.Accepted(i.dir)
	if err != nil {
		return 0, err
	}
	if rep.IsBlocked() {
		return 0, fmt.Errorf("ingest: WAL BLOCKED")
	}
	return len(recs), nil
}

// Progress is the drain backlog + recovery view for /health (F5): how many durable-accepted
// records still await drain processing (Depth); quarantine is processed, not committed, how far the committed watermark
// trails the newest durable sequence (LagSeq), and whether recovery is BLOCKED with ambiguous/
// damaged regions preserved (Blocked/BlockedRegions = observable gaps). It never fails closed on
// a BLOCKED journal: the whole point is to make the gap observable, so it reports Blocked=true
// and still counts the validated prefix.
type Progress struct {
	Accepted       int    // durable-accepted frames in the validated prefix
	Processed      int    // checkpoint-covered frames, including quarantine; not archive commitment
	Depth          int    // accepted frames ABOVE the watermark (drain backlog)
	HighestSeq     uint64 // newest durable sequence in the validated prefix
	CommittedSeq   uint64 // processed checkpoint, including permanent quarantine
	LagSeq         uint64 // HighestSeq - CommittedSeq (0 if caught up)
	Blocked        bool   // recovery BLOCKED (ambiguous/damaged tail preserved, not discarded)
	BlockedRegions int    // count of preserved ambiguous/damaged regions (gaps)
	WALBytes       int64  // current physical journal size
}

// Progress computes the F5 health view. It reads the recovery plan directly (so a BLOCKED
// journal is REPORTED, not turned into an error) and the durable watermark under the lock.
func (i *Ingestor) Progress() (Progress, error) {
	i.mu.Lock()
	defer i.mu.Unlock()
	rep, err := wal.RecoverPlan(i.dir)
	if err != nil {
		return Progress{}, err
	}
	p := Progress{CommittedSeq: i.committed, Blocked: rep.IsBlocked(), BlockedRegions: len(rep.BlockedDx)}
	for _, d := range rep.Replay {
		p.Accepted++
		if d.Seq > p.HighestSeq {
			p.HighestSeq = d.Seq
		}
		if d.Seq > i.committed {
			p.Depth++
		} else {
			p.Processed++
		}
	}
	if p.HighestSeq > p.CommittedSeq {
		p.LagSeq = p.HighestSeq - p.CommittedSeq
	}
	if b, be := i.w.Bytes(); be == nil {
		p.WALBytes = b
	} else {
		return Progress{}, fmt.Errorf("ingest: physical WAL measurement unavailable: %w", be)
	}
	return p, nil
}

// RecordState is the lifecycle state of one idempotency key / receipt (F10), derived from the
// durable WAL + the archive-committed watermark + archive presence (no separate state store):
//   - not_found       : the key is not a durable-accepted record (never accepted, or failed
//     before durable acceptance);
//   - durable_accepted : accepted in the WAL, sequence ABOVE the watermark (awaiting drain);
//   - archive_committed: accepted and drained, and its identity is present in the archive (in the
//     Mongo-only slice this is the terminal state; a separate "indexed" step
//     would require the PG index, which is out of this slice);
//   - quarantined      : accepted and drained, but NOT published (a monotone consent/deletion
//     gate denied it) - it is addressable but intentionally not in the archive;
//   - blocked          : the key lies in an ambiguous/damaged region preserved by recovery;
//   - drained          : BLOCKED-journal fallback only - accepted at/below the watermark but the
//     payload is unreadable while blocked, so archive_committed vs quarantined cannot be told
//     apart (reported as the honest, less-specific "drained").
//
// The response carries NO global watermark/sequence counter (P2-5): only the receipt's own Seq,
// so a scoped lookup never leaks cross-project drain progression. A key whose record belongs to a
// DIFFERENT project reads as not_found (no cross-project existence leak), and an archive read
// error is propagated (never a false "archive_committed"/"not_found").
type RecordState struct {
	LifecycleState string `json:"lifecycle_state,omitempty"`
	Observation    string `json:"observation,omitempty"`
	IndexState     string `json:"index_state,omitempty"`
	Key            string `json:"key"`
	State          string `json:"state"`
	Seq            uint64 `json:"seq"`
	Blocked        bool   `json:"blocked"`
}

func (i *Ingestor) RecordState(key, project string) (RecordState, error) {
	i.mu.Lock()
	defer i.mu.Unlock()
	st := RecordState{Key: key, State: "not_found"}
	recs, rep, err := wal.Accepted(i.dir)
	if err != nil {
		return RecordState{}, err
	}
	if rep.IsBlocked() {
		st.Blocked = true
		// While BLOCKED the frame payloads are not read (they may be the damaged region), so the
		// record's Project cannot be taken from the payload as the normal path does. Enforce the
		// SAME cross-project isolation guard by parsing the Project out of the canonical identity
		// key; if it does not parse to the authorized project (including a legacy opaque key whose
		// project cannot be recovered), report not_found rather than leak existence/state.
		if proj, ok := projectOfIdentityKey(key); !ok || proj != project {
			return RecordState{Key: key, State: "not_found"}, nil
		}
		for _, d := range rep.BlockedDx {
			if d.Key == key {
				st.State, st.Seq = "blocked", d.Seq
				return st, nil
			}
		}
		for _, d := range rep.Replay {
			if d.Key == key {
				st.Seq = d.Seq
				if d.Seq > i.committed {
					st.State = "durable_accepted"
				} else {
					st.State = "drained"
				}
				return st, nil
			}
		}
		return RecordState{Key: key, State: "not_found"}, nil
	}
	// Resolve the receipt to the one durable record by LITERAL stored key first, then by canonical
	// identity (P2-2): a receipt issued under a different supported encoding - e.g. a canonical
	// identity key for a record durably accepted under a legacy delimiter key - must still resolve
	// to that record, not report not_found.
	matched, matchedSeq, err := i.resolveReceipt(recs, key)
	if err != nil {
		return RecordState{}, err
	}
	if matched == nil {
		identity, ok := recordIdentity(key)
		if !ok || identity.Project != project {
			return st, nil
		}
		_, found, e := i.store.Lookup(identity)
		if e != nil {
			return RecordState{}, e
		}
		if found {
			st.State = "archive_committed"
		}
		return st, nil
	}
	if matched.Project != project {
		return RecordState{Key: key, State: "not_found"}, nil // isolation: do not leak
	}
	st.Seq = matchedSeq
	if matchedSeq > i.committed {
		st.State = "durable_accepted"
		return st, nil
	}
	// Drained (seq <= watermark): published to the archive, or quarantined (gate-denied).
	stored, found, ferr := i.store.Lookup(*matched)
	if ferr != nil {
		return RecordState{}, ferr
	}
	if found {
		if stored != *matched {
			return RecordState{}, archive.ErrIDConflict
		}
		for _, rc := range recs {
			if rc.Seq == matchedSeq && rc.Version == 2 {
				same, e := i.verifyEnvelopeSource(rc)
				if e != nil {
					return RecordState{}, e
				}
				if !same {
					return RecordState{}, archive.ErrIDConflict
				}
			}
		}
		st.State = "archive_committed"
		return st, nil
	}
	st.State = "quarantined"
	return st, nil
}

// resolveReceipt finds the accepted record a receipt refers to: by literal stored WAL key first
// (cheapest, no decode), else by canonical identity of the decoded payload (so a legacy-key record
// is found when queried under its canonical identity receipt, and vice versa). Returns (nil,0,nil)
// when no record matches. A corrupt payload is a hard error, never a silent miss.
func (i *Ingestor) resolveReceipt(recs []wal.Record, key string) (*archive.Record, uint64, error) {
	for idx := range recs {
		if recs[idx].Key == key {
			var r archive.Record
			if e := decodeWALRecord(recs[idx], &r); e != nil {
				return nil, 0, fmt.Errorf("ingest: corrupt WAL payload for receipt: %w", e)
			}
			return &r, recs[idx].Seq, nil
		}
	}
	for idx := range recs {
		var r archive.Record
		if e := decodeWALRecord(recs[idx], &r); e != nil {
			return nil, 0, fmt.Errorf("ingest: corrupt WAL payload for receipt: %w", e)
		}
		if archive.IdentityKey(r) == key {
			return &r, recs[idx].Seq, nil
		}
	}
	return nil, 0, nil
}

// projectOfIdentityKey recovers the Project from a canonical identity key (the JSON array
// [Project, SourceInstance, SessionID, MessageID] produced by archive.IdentityKey). It returns
// ok=false for anything that is not such an array (e.g. a legacy opaque delimiter key), so a
// caller that needs the project for an isolation decision can fail closed instead of guessing.
func projectOfIdentityKey(key string) (string, bool) {
	var parts []string
	if err := json.Unmarshal([]byte(key), &parts); err != nil || len(parts) != 4 {
		return "", false
	}
	return parts[0], true
}

// Query reads archived records for one project. It fails closed when the archive is
// unavailable (returns archive.ErrUnavailable, never an empty "no history"). The caller is
// responsible for applying the retention/consent serve-gate to the returned hits before
// serving them to a principal (see the API layer).
func (i *Ingestor) Query(project, substr, provider string) ([]archive.Hit, error) {
	recs, err := i.store.Fetch(project)
	if err != nil {
		return nil, err // propagate the real read error (never an empty "no history")
	}
	return archive.Query(recs, substr, provider), nil
}

// Store exposes the bound archive store (for the serve-gate layer).
func (i *Ingestor) Store() archive.Store { return i.store }

// ReservationBytes is a monotonic generation-local ledger for stale measurements.
// PendingArchiveBytes is rebuilt from durable unprocessed WAL records on restart.
func (i *Ingestor) ReservationBytes() int64 {
	i.mu.Lock()
	defer i.mu.Unlock()
	return i.reservationTotal
}
func (i *Ingestor) PendingArchiveBytes() int64 {
	i.mu.Lock()
	defer i.mu.Unlock()
	return i.pendingArchiveBytes
}
