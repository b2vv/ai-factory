package ingest

import (
	"aifactory.local/storage/internal/archive"
	"aifactory.local/storage/internal/config"
	"aifactory.local/storage/internal/wal"
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"time"
)

// Reclaim removes only checkpoint-covered records verified byte-for-byte in the
// authoritative archive. Quarantine, pending records and ambiguous journals remain.
// Canonical receipt and dedup lookup fall back to that same archive after reclamation.
func (i *Ingestor) Reclaim() (CompactOutcome, error) { return i.ReclaimGated(nil) }

// ReclaimGated additionally preserves records currently withheld by policy, even
// if an older authoritative archive copy exists. Caller holds the authority fence.
func (i *Ingestor) ReclaimGated(eligible func(archive.Record) bool) (CompactOutcome, error) {
	return i.ReclaimBudgeted(eligible, i.acct.WALMaintenanceLimit())
}

// ReclaimBudgeted applies the caller's measured live/free staging ceiling in
// addition to the configured WAL cap. Caller serializes other resource writers.
func (i *Ingestor) ReclaimBudgeted(eligible func(archive.Record) bool, peakLimit int64) (CompactOutcome, error) {
	i.mu.Lock()
	return i.reclaimBudgetedLocked(eligible, peakLimit)
}

// ReclaimWithUsage is explicit maintenance, not background activation. The caller
// holds the cross-writer authority fence and supplies a reconciled measurement.
// Pending archive debt is read under the same lock as generation selection/flip.
func (i *Ingestor) ReclaimWithUsage(eligible func(archive.Record) bool, usage config.Usage) (CompactOutcome, error) {
	i.mu.Lock()
	current, e := wal.ManagedBytes(i.dir)
	if e != nil {
		i.mu.Unlock()
		return CompactOutcome{}, e
	}
	peak, e := i.acct.MaintenancePeakWithPending(usage, current, i.pendingArchiveBytes)
	if e != nil {
		i.mu.Unlock()
		return CompactOutcome{}, fmt.Errorf("%w: %v", wal.ErrMaintenanceBudget, e)
	}
	return i.reclaimBudgetedLocked(eligible, peak)
}

// Consumes the held ingest lock and releases it on every path.
func (i *Ingestor) reclaimBudgetedLocked(eligible func(archive.Record) bool, peakLimit int64) (CompactOutcome, error) {
	if peakLimit <= 0 {
		i.mu.Unlock()
		return CompactOutcome{}, wal.ErrMaintenanceBudget
	}
	if peakLimit > i.acct.WALMaintenanceLimit() {
		peakLimit = i.acct.WALMaintenanceLimit()
	}
	var err error
	if i.reclaimScan == nil {
		i.reclaimScan, err = wal.NewScanner(i.dir, i.acct.WALMaintenanceLimit())
		if err != nil {
			i.mu.Unlock()
			return CompactOutcome{}, err
		}
	}
	recs, done, err := i.reclaimScan.Next(128, 16<<20)
	if err != nil {
		i.reclaimScan = nil
		i.mu.Unlock()
		if errors.Is(err, wal.ErrScanChanged) {
			return CompactOutcome{}, nil
		}
		return CompactOutcome{}, err
	}
	if done {
		i.reclaimScan = nil
	}
	drop := map[string]archive.Record{}
	deadline := time.Now().Add(2 * time.Second)
	for _, rc := range recs {
		if time.Now().After(deadline) {
			break
		}
		if rc.Seq <= i.reclaimAfter {
			continue
		}
		i.reclaimAfter = rc.Seq
		if rc.Seq > i.committed {
			continue
		}
		var r archive.Record
		if err = json.Unmarshal(rc.Payload, &r); err != nil {
			i.mu.Unlock()
			return CompactOutcome{}, err
		}
		if eligible != nil && !eligible(r) {
			continue
		}
		// Opaque historical receipt aliases are not reconstructible from an archive identity.
		// Keep their WAL evidence until explicit purge; never silently invalidate them.
		if rc.Key != archive.IdentityKey(r) {
			continue
		}
		stored, found, e := i.store.Lookup(r)
		if e != nil {
			i.mu.Unlock()
			return CompactOutcome{}, e
		}
		if found && stored == r {
			drop[archive.IdentityKey(r)] = r
		}
	}
	if done {
		i.reclaimAfter = 0
	}
	if len(drop) == 0 {
		i.mu.Unlock()
		return CompactOutcome{}, nil
	}
	// The complete-generation transition remains bounded by the configured
	// input cap; selection above is incremental and never materializes all payloads.
	all, rep, e := wal.AcceptedWithin(i.dir, i.acct.WALMaintenanceLimit())
	if e != nil || rep.IsBlocked() {
		i.mu.Unlock()
		if e != nil {
			return CompactOutcome{}, e
		}
		return CompactOutcome{}, fmt.Errorf("ingest: reclaim refused on BLOCKED WAL")
	}
	keepRaw := func(key string, payload []byte) bool {
		var r archive.Record
		if json.Unmarshal(payload, &r) != nil {
			return true
		}
		stored, ok := drop[archive.IdentityKey(r)]
		return !ok || stored != r
	}
	budget := wal.MaintenanceBudget{MaxInputBytes: i.acct.WALMaintenanceLimit(), MaxPeakBytes: peakLimit}
	// 64 bytes bounds the JSON watermark replacement; 3 bytes covers the marker.
	plan, e := wal.PlanCompaction(i.dir, all, keepRaw, budget, 67)
	if e != nil {
		i.mu.Unlock()
		return CompactOutcome{}, e
	}
	if e = i.reserveMaintenance(all, keepRaw, plan.PeakBytes-plan.InputBytes); e != nil {
		i.mu.Unlock()
		return CompactOutcome{}, e
	}
	i.reclaimScan = nil
	// Persist the need for archive dedup BEFORE dropping any WAL evidence. An
	// interrupted marker write causes Open to refuse, never silently forget dedup.
	if !i.hasReclaimed {
		f, e := os.OpenFile(filepath.Join(i.dir, "reclaimed"), os.O_CREATE|os.O_RDWR, 0600)
		if e != nil {
			i.mu.Unlock()
			return CompactOutcome{}, e
		}
		old, readErr := os.ReadFile(filepath.Join(i.dir, "reclaimed"))
		if readErr != nil {
			f.Close()
			i.mu.Unlock()
			return CompactOutcome{}, readErr
		}
		if len(old) > 0 && string(old) != "v1\n" {
			f.Close()
			i.mu.Unlock()
			return CompactOutcome{}, fmt.Errorf("invalid reclamation marker")
		}
		_, e = f.WriteAt([]byte("v1\n"), 0)
		if e == nil {
			e = f.Sync()
		}
		f.Close()
		if e == nil {
			var d *os.File
			d, e = os.Open(i.dir)
			if e == nil {
				e = d.Sync()
				d.Close()
			}
		}
		if e != nil {
			i.mu.Unlock()
			return CompactOutcome{}, e
		}
		i.hasReclaimed = true
	}
	// Keep the reservation fence through the transition: a concurrent Accept
	// cannot consume the reserved staging bytes between preflight and the flip.
	defer i.mu.Unlock()
	return i.compactLocked(func(r archive.Record) bool { stored, ok := drop[archive.IdentityKey(r)]; return !ok || stored != r })
}

func (i *Ingestor) WALBytes() int64 { i.mu.Lock(); defer i.mu.Unlock(); return i.walBytes }
func recordIdentity(key string) (archive.Record, bool) {
	var v []string
	if json.Unmarshal([]byte(key), &v) != nil || len(v) != 4 {
		return archive.Record{}, false
	}
	return archive.Record{Project: v[0], SourceInstance: v[1], SessionID: v[2], MessageID: v[3]}, true
}

// MaintenanceBytes includes current journal and maintenance/checkpoint metadata.
func (i *Ingestor) MaintenanceBytes() (int64, error) {
	i.mu.Lock()
	defer i.mu.Unlock()
	return wal.ManagedBytes(i.dir)
}
