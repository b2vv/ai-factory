package control

import (
	"crypto/sha256"
	"encoding/hex"
	"fmt"
	"path/filepath"

	"aifactory.local/storage/internal/budget"
	"aifactory.local/storage/internal/wal"
)

func budgetHash(raw []byte) string { h := sha256.Sum256(raw); return hex.EncodeToString(h[:]) }

// AttachBudget transfers ownership of an exclusively opened accounting ledger.
// It is called before requests/workers. A pending control intent is reconciled
// only against the accepted journal and its repaired high-water marker.
func (d *Durable) AttachBudget(l *budget.Ledger) error {
	d.mu.Lock()
	defer d.mu.Unlock()
	if d.budget != nil {
		return fmt.Errorf("control: accounting already attached")
	}
	d.budget = l
	pending := l.Snapshot().Pending
	if len(pending) == 0 {
		return nil
	}
	for _, p := range pending {
		if p.Evidence.Kind != "control" {
			return nil
		}
	}
	recs, rep, e := wal.Accepted(filepath.Join(d.stateDir, "wal"))
	if e != nil {
		return e
	}
	if rep.IsBlocked() {
		return budget.ErrBlocked
	}
	return l.Recover(func(p budget.Intent) (bool, error) {
		for _, r := range recs {
			if r.Seq <= d.highWater && budgetHash([]byte(r.Key)) == p.Evidence.KeyHash && budgetHash(r.Payload) == p.Evidence.PayloadHash {
				return true, nil
			}
		}
		return false, nil
	})
}

// FinishExternal is explicit: a nil callback result alone is not success (HTTP
// handlers may encode a failure response). Call only after verified durable IO.
func (d *Durable) FinishExternal() error {
	if d.budget == nil {
		return nil
	}
	if !d.externalActive {
		if len(d.budget.Snapshot().Pending) > 0 {
			return budget.ErrBlocked
		}
		return nil
	}
	e := d.budget.Finish()
	if e == nil {
		d.externalActive = false
	}
	return e
}
func (d *Durable) Budget() *budget.Ledger { return d.budget }

// RegisterManagedPath is called only inside the shared authority/write fence.
func (d *Durable) RegisterManagedPath(path, prefix string) error {
	if d.budget == nil {
		return nil
	}
	return budget.RegisterPath(d.stateDir, path, prefix, d.budget)
}

// ReserveIdentifiedExternal supports an idempotent derived write whose exact
// identity/payload can be reverified after an ambiguous backend result.
func (d *Durable) ReserveIdentifiedExternal(evidence budget.Evidence, cost int64) error {
	if d.budget == nil {
		return d.ReserveExternalBytes(cost)
	}
	if len(d.budget.Snapshot().Pending) > 0 {
		if e := d.budget.Resume(evidence); e != nil {
			return e
		}
		d.externalActive = true
		return nil
	}
	if e := d.admitGrowth(cost, 0); e != nil {
		return e
	}
	if e := d.budget.Reserve(evidence, cost); e != nil {
		return e
	}
	d.externalActive = true
	d.externalReserved.Add(cost)
	d.reserved.Add(cost)
	return nil
}
