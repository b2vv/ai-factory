package wal

import (
	"errors"
	"fmt"
	"math"
	"os"
	"path/filepath"
)

var ErrMaintenanceBudget = errors.New("wal: maintenance budget exceeded; journal preserved")

// MaintenanceBudget bounds both read work and peak managed file bytes. It does
// not claim a filesystem block-allocation quota or a wall-clock fsync deadline.
// Zero/negative limits refuse; callers must explicitly supply their current cap.
type MaintenanceBudget struct {
	MaxInputBytes int64
	MaxPeakBytes  int64
}
type CompactionBudget struct{ InputBytes, StagedBytes, PeakBytes int64 }

// ManagedBytes includes both generations and transition/checkpoint metadata.
// The journal is a private directory with at most one staging subdirectory.
// Unexpected types or excessive entries refuse rather than undercount.
func ManagedBytes(dir string) (int64, error) {
	var total int64
	entries := 0
	err := filepath.WalkDir(dir, func(path string, d os.DirEntry, e error) error {
		if e != nil {
			return e
		}
		if path == dir {
			return nil
		}
		entries++
		if entries > 32 {
			return fmt.Errorf("wal: excessive maintenance files")
		}
		rel, e := filepath.Rel(dir, path)
		if e != nil {
			return e
		}
		if d.IsDir() {
			if rel != compactStaging {
				return fmt.Errorf("wal: unexpected journal directory")
			}
			return nil
		}
		st, e := d.Info()
		if e != nil {
			return e
		}
		if !st.Mode().IsRegular() {
			return fmt.Errorf("wal: nonregular journal file")
		}
		if st.Size() > math.MaxInt64-total {
			return ErrMaintenanceBudget
		}
		total += st.Size()
		return nil
	})
	return total, err
}

// AcceptedWithin checks the size BEFORE RecoverPlan's existing allocations. The
// authoritative recovery classifier remains unchanged, including preserve+BLOCK.
func AcceptedWithin(dir string, maxBytes int64) ([]Record, Report, error) {
	n, e := ManagedBytes(dir)
	if e != nil {
		return nil, Report{}, e
	}
	if maxBytes <= 0 || n > maxBytes {
		return nil, Report{}, fmt.Errorf("%w: input %d > %d", ErrMaintenanceBudget, n, maxBytes)
	}
	return Accepted(dir)
}

// PlanCompaction performs no writes. Keep must be deterministic for the lifetime
// of the caller's exclusive journal lock. CheckpointScratch reserves space for a
// caller's pre-flip checkpoint replacement; it remains charged conservatively
// alongside staging even though these writes normally do not overlap.
func PlanCompaction(dir string, recs []Record, keep func(string, []byte) bool, b MaintenanceBudget, checkpointScratch int64) (CompactionBudget, error) {
	var p CompactionBudget
	n, e := ManagedBytes(dir)
	if e != nil {
		return p, e
	}
	p.InputBytes = n
	if b.MaxInputBytes <= 0 || n > b.MaxInputBytes || b.MaxPeakBytes <= 0 || checkpointScratch < 0 {
		return p, ErrMaintenanceBudget
	}
	for _, r := range recs {
		if keep != nil && !keep(r.Key, r.Payload) {
			continue
		}
		cost := int64(21 + len(r.Key) + len(r.Payload) + intentSize + acceptSize + 16 + len(r.Key))
		if cost > math.MaxInt64-p.StagedBytes {
			return p, ErrMaintenanceBudget
		}
		p.StagedBytes += cost
	}
	extra := int64(len(sentinelBytes)) + checkpointScratch
	if extra > math.MaxInt64-p.StagedBytes || p.StagedBytes+extra > math.MaxInt64-n {
		return p, ErrMaintenanceBudget
	}
	p.PeakBytes = n + p.StagedBytes + extra
	if p.PeakBytes > b.MaxPeakBytes {
		return p, fmt.Errorf("%w: peak %d > %d", ErrMaintenanceBudget, p.PeakBytes, b.MaxPeakBytes)
	}
	return p, nil
}

// CompactWithin preserves the existing on-disk format and sentinel protocol.
// It refuses before staging if the complete old+new generation cannot fit.
func CompactWithin(dir string, keep func(string, []byte) bool, b MaintenanceBudget) (CompactResult, error) {
	recs, rep, e := AcceptedWithin(dir, b.MaxInputBytes)
	if e != nil {
		return CompactResult{}, e
	}
	if rep.IsBlocked() {
		return CompactResult{}, fmt.Errorf("wal: maintenance refused on BLOCKED journal")
	}
	if _, e = PlanCompaction(dir, recs, keep, b, 0); e != nil {
		return CompactResult{}, e
	}
	return Compact(dir, keep)
}
