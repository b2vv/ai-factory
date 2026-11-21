package control

import (
	"aifactory.local/storage/internal/archive"
	"aifactory.local/storage/internal/budget"
	"aifactory.local/storage/internal/registry"
	"aifactory.local/storage/internal/wal"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"math"
	"strconv"
)

// ArchiveProjection is a durable exact request for the derived PG checkpoint.
// It contains no message text. Rebuild tokens are generated once before reserve.
type ArchiveProjection struct {
	Action            string
	Expected, Desired archive.IndexCheckpoint
	Identity          archive.Record
	EnvelopeHash      string
}

func projectionEvidence(p ArchiveProjection) budget.Evidence {
	raw, _ := json.Marshal(p)
	return budget.Evidence{Kind: "archive-index-v2", KeyHash: budgetHash([]byte(p.Desired.Project)), PayloadHash: budgetHash(raw)}
}
func validProjection(p ArchiveProjection, state ArchiveState, project string) bool {
	d, e := p.Desired, p.Expected
	if d.Project != project || d.SourceGeneration != state.Generation || d.PolicyRevision != strconv.FormatUint(state.PolicyRevision, 10) || !validArchiveGeneration(d.ProjectionGeneration) || d.Ordinal < 0 || d.Ordinal > state.CommittedOrdinal {
		return false
	}
	if p.Action == "rebuild" {
		if p.EnvelopeHash != "" || p.Identity != (archive.Record{}) {
			return false
		}

		if d.Ordinal != 0 || d.Complete {
			return false
		}
		if e.Project == "" {
			return e == (archive.IndexCheckpoint{})
		}
		_, err := strconv.ParseUint(e.PolicyRevision, 10, 64)
		return err == nil && e.Project == project && validArchiveGeneration(e.SourceGeneration) && validArchiveGeneration(e.ProjectionGeneration) && e.Ordinal >= 0 && e.ProjectionGeneration != d.ProjectionGeneration

	}
	if e.Project != d.Project || e.SourceGeneration != d.SourceGeneration || e.ProjectionGeneration != d.ProjectionGeneration || e.PolicyRevision != d.PolicyRevision || e.Ordinal < 0 || d.Ordinal < e.Ordinal {
		return false
	}
	switch p.Action {
	case "project":
		hash, err := hex.DecodeString(p.EnvelopeHash)
		identity := archive.Record{Project: p.Identity.Project, SourceInstance: p.Identity.SourceInstance, SessionID: p.Identity.SessionID, MessageID: p.Identity.MessageID}
		return err == nil && len(hash) == 32 && identity == p.Identity && identity.Project == project && !d.Complete && d.Ordinal > e.Ordinal
	case "advance":
		return p.EnvelopeHash == "" && p.Identity == (archive.Record{}) && !d.Complete && d.Ordinal > e.Ordinal
	case "complete":
		return p.EnvelopeHash == "" && p.Identity == (archive.Record{}) && d.Complete && d.Ordinal == state.CommittedOrdinal
	}
	return false
}
func (d *Durable) applyArchiveProjection(m mutation) error {
	state, ok := d.archiveStates[m.Project]
	if !ok || m.ArchiveProjection == nil || !validProjection(*m.ArchiveProjection, state, m.Project) || (m.ProjectionCancellationBytes != 0 && m.ProjectionCancellationBytes != projectionCancellationCost(*m.ArchiveProjection)) {
		return ErrBlocked
	}
	detached := *m.ArchiveProjection
	state.Projection = &detached
	state.ProjectionCancelled = false
	state.ProjectionCancellationBytes = m.ProjectionCancellationBytes
	d.archiveStates[m.Project] = state
	return nil
}
func (t *ArchiveTransaction) ReserveProjection(p ArchiveProjection, cost int64) error {
	if err := t.ready(); err != nil {
		return err
	}
	state := t.d.archiveStates[t.project]
	if state.ProjectionCancelled && state.Projection != nil && *state.Projection == p {
		return ErrBlocked
	}
	if !validProjection(p, state, t.project) || cost < 0 {
		return ErrBlocked
	}
	evidence := projectionEvidence(p)
	pending := t.d.budget.Snapshot().Pending
	if len(pending) > 0 {
		op, err := t.RecoveryProjection()
		if err != nil {
			return err
		}
		if op == nil || *op != p {
			return budget.ErrBlocked
		}
		return t.d.budget.Resume(evidence)
	}
	cancelCost := projectionCancellationCost(p)
	m := mutation{Kind: kArchiveProjection, Project: t.project, ArchiveProjection: &p, ProjectionCancellationBytes: cancelCost}
	raw, _ := json.Marshal(m)
	key := "archive-index-v2:" + evidence.PayloadHash
	meta, _ := json.Marshal(metaFile{Initialized: true, HighWater: ^uint64(0)})
	controlCost := wal.RecordCost(key, raw) + 2*int64(len(meta))
	if cancelCost > math.MaxInt64-controlCost {
		return ErrCapacity
	}
	controlCost += cancelCost
	if cost > math.MaxInt64-controlCost {
		return ErrCapacity
	}
	if err := t.d.admitGrowth(cost+controlCost, controlCost); err != nil {
		return err
	}
	if err := t.d.budget.Reserve(evidence, cost+controlCost); err != nil {
		return err
	}
	receipt, err := t.d.w.Accept(key, raw)
	if err != nil {
		t.d.block("archive projection receipt uncertain")
		return fmt.Errorf("%w: %v", ErrPersistence, err)
	}
	if receipt.Seq > t.d.highWater {
		t.d.highWater = receipt.Seq
		if err := writeMeta(t.d.metaPath, metaFile{Initialized: true, HighWater: receipt.Seq}); err != nil {
			t.d.block("archive projection marker uncertain")
			return err
		}
	}
	if !receipt.Duplicate {
		return t.d.apply(registry.Principal{Kind: registry.Operator}, m)
	}
	return nil
}
func (t *ArchiveTransaction) RecoveryProjection() (*ArchiveProjection, error) {
	if err := t.ready(); err != nil {
		return nil, err
	}
	pending := t.d.budget.Snapshot().Pending
	if len(pending) == 0 {
		return nil, nil
	}
	if len(pending) != 1 {
		return nil, budget.ErrBlocked
	}
	p := t.d.archiveStates[t.project].Projection
	if p == nil || projectionEvidence(*p) != pending[0].Evidence {
		return nil, nil
	}
	if err := t.d.budget.Resume(projectionEvidence(*p)); err != nil {
		return nil, err
	}
	detached := *p
	return &detached, nil
}
func (t *ArchiveTransaction) FinishProjection(p ArchiveProjection, verify func() error) error {
	if err := t.ready(); err != nil {
		return err
	}
	if t.d.archiveStates[t.project].ProjectionCancelled {
		return ErrBlocked
	}
	if verify == nil {
		return ErrBlocked
	}
	op, err := t.RecoveryProjection()
	if err != nil {
		return err
	}
	if op == nil || *op != p {
		return budget.ErrBlocked
	}
	if err := verify(); err != nil {
		return err
	}
	return t.d.budget.Finish()
}

// ProjectionPending is a read-only freshness check; it does not refresh or
// release the budget intent and does not use an old receipt as pending evidence.
func (t *ArchiveTransaction) ProjectionPending() (bool, error) {
	if err := t.ready(); err != nil {
		return false, err
	}
	pending := t.d.budget.Snapshot().Pending
	p := t.d.archiveStates[t.project].Projection
	return len(pending) == 1 && p != nil && projectionEvidence(*p) == pending[0].Evidence, nil
}
