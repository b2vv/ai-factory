package control

import (
	"aifactory.local/storage/internal/wal"
	"encoding/json"
	"fmt"
)

const kSummaryProjectionCancel mutationKind = "archive_summary_projection_cancel_v1"

func projectionCancellationMutation(p ArchiveProjection) mutation {
	return mutation{Kind: kSummaryProjectionCancel, Project: p.Desired.Project, ArchiveProjection: &p}
}
func projectionCancellationKey(p ArchiveProjection) string {
	return "archive-index-cancel-v1:" + projectionEvidence(p).PayloadHash
}
func projectionCancellationCost(p ArchiveProjection) int64 {
	raw, _ := json.Marshal(projectionCancellationMutation(p))
	meta, _ := json.Marshal(metaFile{Initialized: true, HighWater: ^uint64(0)})
	return wal.RecordCost(projectionCancellationKey(p), raw) + 2*int64(len(meta))
}
func (d *Durable) applyProjectionCancellation(m mutation) error {
	state, found := d.archiveStates[m.Project]
	if !found || m.ArchiveProjection == nil || state.Projection == nil || *state.Projection != *m.ArchiveProjection || m.Project != m.ArchiveProjection.Desired.Project || state.ProjectionCancellationBytes != projectionCancellationCost(*m.ArchiveProjection) {
		return ErrBlocked
	}
	state.ProjectionCancelled = true
	d.archiveStates[m.Project] = state
	return nil
}

// BeginProjectionCancellation retains exact cancellation before any destructive
// derived cleanup. It resumes the original liability, never reserves or refunds a
// different intent. Caller establishes permanent denial; outages must not call it.
func (t *ArchiveTransaction) BeginProjectionCancellation(p ArchiveProjection) error {
	saved, err := t.RecoveryProjection()
	if err != nil {
		return err
	}
	if saved == nil || *saved != p {
		return ErrBlocked
	}
	state := t.d.archiveStates[t.project]
	cost := projectionCancellationCost(p)
	pending := t.d.budget.Snapshot().Pending
	if state.ProjectionCancellationBytes != cost || len(pending) != 1 || pending[0].Bytes < cost {
		return fmt.Errorf("%w: older pending projection lacks reserved cancellation capacity", ErrCapacity)
	}
	if state.ProjectionCancelled {
		return nil
	}
	raw, _ := json.Marshal(projectionCancellationMutation(p))
	receipt, err := t.d.w.Accept(projectionCancellationKey(p), raw)
	if err != nil {
		t.d.block("projection cancellation persistence uncertain")
		return fmt.Errorf("%w: %v", ErrPersistence, err)
	}
	if receipt.Seq > t.d.highWater {
		t.d.highWater = receipt.Seq
		if err := writeMeta(t.d.metaPath, metaFile{Initialized: true, HighWater: receipt.Seq}); err != nil {
			t.d.block("projection cancellation marker uncertain")
			return fmt.Errorf("%w: %v", ErrPersistence, err)
		}
	}
	if !receipt.Duplicate {
		return t.d.applyProjectionCancellation(projectionCancellationMutation(p))
	}
	if !t.d.archiveStates[t.project].ProjectionCancelled {
		return ErrBlocked
	}
	return nil
}

func (t *ArchiveTransaction) ProjectionCancellation(p ArchiveProjection) (bool, error) {
	if err := t.ready(); err != nil {
		return false, err
	}
	state := t.d.archiveStates[t.project]
	if state.Projection == nil || *state.Projection != p {
		return false, ErrBlocked
	}
	return state.ProjectionCancelled, nil
}

// FinishCancelledProjection requires both the retained cancellation and positive
// proof that only this project's derived rows/checkpoint were removed. SQL cleanup
// and its proof are idempotent; any uncertainty keeps the same ledger intent.
func (t *ArchiveTransaction) FinishCancelledProjection(p ArchiveProjection, verify func() error) error {
	if verify == nil {
		return ErrBlocked
	}
	saved, err := t.RecoveryProjection()
	if err != nil {
		return err
	}
	cancelled, err := t.ProjectionCancellation(p)
	if err != nil {
		return err
	}
	if saved == nil || *saved != p || !cancelled {
		return ErrBlocked
	}
	if err := verify(); err != nil {
		return err
	}
	return t.d.budget.Finish()
}
