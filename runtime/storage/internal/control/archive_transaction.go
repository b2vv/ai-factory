package control

import (
	"aifactory.local/storage/internal/archive"
	"aifactory.local/storage/internal/budget"
	"aifactory.local/storage/internal/registry"
	"aifactory.local/storage/internal/wal"
	"encoding/json"
	"errors"
	"fmt"
	"math"
	"path/filepath"
	"time"
)

// ArchiveOperation retains identity/hash and immutable metadata, never source text.
// All phases share one budget intent; no phase may reserve an unrelated intent.
type ArchiveOperation struct {
	Identity     archive.Record
	RecordHash   string
	Metadata     archive.Metadata
	EnvelopeHash string
}
type ArchiveTransaction struct {
	d       *Durable
	project string
	active  bool
}

func (d *Durable) WithArchiveTransaction(actor registry.Principal, project string, action func(*ArchiveTransaction) error) error {
	if action == nil {
		return errors.New("control: missing archive transaction")
	}
	return d.WithArchiveWriter(actor, project, func(tx *ArchiveTransaction) error {
		if tx == nil {
			return errors.New("control: metadata migration not begun")
		}
		return action(tx)
	})
}

func (t *ArchiveTransaction) ready() error {
	if !t.active {
		return ErrBlocked
	}
	return t.d.ready()
}
func archiveRecordHash(r archive.Record) string { raw, _ := json.Marshal(r); return budgetHash(raw) }
func operationEnvelope(op *ArchiveOperation, r archive.Record) (archive.Envelope, error) {
	if op == nil || archive.IdentityKey(op.Identity) != archive.IdentityKey(r) || op.RecordHash != archiveRecordHash(r) {
		return archive.Envelope{}, archive.ErrIDConflict
	}
	e := archive.Envelope{Version: 2, Record: r, Metadata: op.Metadata}
	raw, err := archive.EncodeEnvelope(e)
	if err != nil {
		return archive.Envelope{}, err
	}
	if budgetHash(raw) != op.EnvelopeHash {
		return archive.Envelope{}, archive.ErrIDConflict
	}
	return archive.DecodeEnvelope(2, raw)
}
func operationEvidence(op *ArchiveOperation) budget.Evidence {
	return budget.Evidence{Kind: "archive-source-v2", KeyHash: budgetHash([]byte(archive.IdentityKey(op.Identity))), PayloadHash: op.EnvelopeHash}
}
func phaseMutation(kind mutationKind, op *ArchiveOperation) mutation {
	return mutation{Kind: kind, Project: op.Identity.Project, ArchiveOperation: op}
}
func phaseKey(kind mutationKind, op *ArchiveOperation) string {
	return fmt.Sprintf("archive-v2:%s:%d:%s:%s", budgetHash([]byte(op.Identity.Project)), op.Metadata.Ordinal, op.Metadata.Generation, kind)
}
func (t *ArchiveTransaction) Reserve(r archive.Record, sourceTime *time.Time, legacy bool) (archive.Envelope, error) {
	if err := t.ready(); err != nil {
		return archive.Envelope{}, err
	}
	if r.Project != t.project {
		return archive.Envelope{}, archive.ErrIDConflict
	}
	state := t.d.archiveStates[t.project]
	if state.Pending != nil {
		e, err := operationEnvelope(state.Pending, r)
		if err != nil {
			return archive.Envelope{}, err
		}
		if legacy != e.Metadata.Legacy {
			return archive.Envelope{}, archive.ErrIDConflict
		}
		if sourceTime != nil && e.Metadata.SourceEventTime != nil && !sourceTime.Equal(*e.Metadata.SourceEventTime) {
			return archive.Envelope{}, archive.ErrIDConflict
		}
		if t.d.budget != nil {
			if err := t.d.budget.Resume(operationEvidence(state.Pending)); err != nil {
				return archive.Envelope{}, err
			}
		}
		return e, nil
	}
	if legacy == state.MigrationComplete || state.NextOrdinal < 1 || state.NextOrdinal == math.MaxInt64 {
		return archive.Envelope{}, errors.New("control: archive reservation unavailable")
	}
	m := archive.Metadata{Generation: state.Generation, Ordinal: state.NextOrdinal, Legacy: legacy, SourceEventTime: sourceTime}
	if !legacy {
		now := time.Now().UTC()
		m.CapturedAt = &now
	}
	e := archive.Envelope{Version: 2, Record: r, Metadata: m}
	raw, err := archive.EncodeEnvelope(e)
	if err != nil {
		return archive.Envelope{}, err
	}
	e, err = archive.DecodeEnvelope(2, raw)
	if err != nil {
		return archive.Envelope{}, err
	}
	op := &ArchiveOperation{Identity: archive.Record{Project: r.Project, SourceInstance: r.SourceInstance, SessionID: r.SessionID, MessageID: r.MessageID}, RecordHash: archiveRecordHash(r), Metadata: e.Metadata, EnvelopeHash: budgetHash(raw)}
	cost, err := archive.EnvelopeReservationBytes(e)
	if err != nil {
		return archive.Envelope{}, err
	}
	cost += wal.RecordCost(archive.IdentityKey(r), raw) + 128 // processed marker and its staging copy
	var controlCost int64
	for _, kind := range []mutationKind{kArchiveReserve, kArchiveCommit, kArchiveCancel} {
		payload, _ := json.Marshal(phaseMutation(kind, op))
		controlCost += wal.RecordCost(phaseKey(kind, op), payload)
	}
	meta, _ := json.Marshal(metaFile{Initialized: true, HighWater: ^uint64(0)})
	controlCost += int64(len(meta)) * 2
	cost += controlCost
	if err := t.d.admitGrowth(cost, controlCost); err != nil {
		return archive.Envelope{}, err
	}
	if t.d.budget != nil {
		if err := t.d.budget.Reserve(operationEvidence(op), cost); err != nil {
			return archive.Envelope{}, err
		}
	}
	if err := t.persistPhase(kArchiveReserve, op); err != nil {
		return archive.Envelope{}, err
	}
	return e, nil
}
func (t *ArchiveTransaction) persistPhase(kind mutationKind, op *ArchiveOperation) error {
	if t.d.budget != nil {
		if err := t.d.budget.Resume(operationEvidence(op)); err != nil {
			return err
		}
	}
	m := phaseMutation(kind, op)
	payload, _ := json.Marshal(m)
	rcpt, err := t.d.w.Accept(phaseKey(kind, op), payload)
	if err != nil {
		t.d.block("archive control phase persistence uncertain")
		return fmt.Errorf("%w: %v", ErrPersistence, err)
	}
	if rcpt.Seq > t.d.highWater {
		t.d.highWater = rcpt.Seq
		if err := writeMeta(t.d.metaPath, metaFile{Initialized: true, HighWater: rcpt.Seq}); err != nil {
			t.d.block("archive control marker persistence uncertain")
			return fmt.Errorf("%w: %v", ErrPersistence, err)
		}
	}
	if !rcpt.Duplicate {
		return t.d.apply(registry.Principal{Kind: registry.Operator}, m)
	}
	return nil
}

// Complete verifies source projection before commitment, then processing before
// releasing the shared liability. Failed verification never advances commitment.
func (t *ArchiveTransaction) Complete(r archive.Record, verify func(archive.Envelope) error, processed func() error) error {
	if err := t.ready(); err != nil {
		return err
	}
	if verify == nil || processed == nil || r.Project != t.project {
		return ErrBlocked
	}
	state := t.d.archiveStates[t.project]
	op := state.Pending
	if op == nil {
		if !state.LastCommitted {
			return ErrBlocked
		}
		op = state.Last
	}
	e, err := operationEnvelope(op, r)
	if err != nil {
		return err
	}
	if t.d.budget != nil {
		if err := t.d.budget.Resume(operationEvidence(op)); err != nil {
			return err
		}
	}
	if err := verify(e); err != nil {
		return err
	}
	if state.Pending != nil {
		if err := t.persistPhase(kArchiveCommit, op); err != nil {
			return err
		}
	}
	if err := processed(); err != nil {
		return err
	}
	if t.d.budget != nil {
		return t.d.budget.Finish()
	}
	return nil
}
func (d *Durable) applyArchivePhase(m mutation) error {
	op := m.ArchiveOperation
	state, ok := d.archiveStates[m.Project]
	if !ok || op == nil || op.Identity.Project != m.Project || op.Metadata.Generation != state.Generation {
		return ErrBlocked
	}
	switch m.Kind {
	case kArchiveReserve:
		if state.Pending != nil || op.Metadata.Ordinal != state.NextOrdinal || state.NextOrdinal == math.MaxInt64 {
			return ErrBlocked
		}
		raw, _ := json.Marshal(op)
		var detached ArchiveOperation
		if err := json.Unmarshal(raw, &detached); err != nil {
			return err
		}
		state.Pending = &detached
		state.Last = nil
		state.LastCommitted = false
		state.NextOrdinal++
	case kArchiveCommit, kArchiveCancel:
		a, _ := json.Marshal(state.Pending)
		b, _ := json.Marshal(op)
		if state.Pending == nil || string(a) != string(b) {
			return ErrBlocked
		}
		state.Pending = nil
		state.Last = op
		state.LastCommitted = m.Kind == kArchiveCommit
		if m.Kind == kArchiveCommit {
			state.CommittedOrdinal = op.Metadata.Ordinal
		}
	default:
		return ErrBlocked
	}
	d.archiveStates[m.Project] = state
	return nil
}

func (t *ArchiveTransaction) FinishMigration(verify func(ArchiveState) error) error {
	if err := t.ready(); err != nil {
		return err
	}
	s := t.d.archiveStates[t.project]
	if s.Pending != nil || verify == nil {
		return ErrBlocked
	}
	if t.d.budget != nil && len(t.d.budget.Snapshot().Pending) != 0 {
		return budget.ErrBlocked
	}
	if s.MigrationComplete {
		return nil
	}
	raw, _ := json.Marshal(s)
	var detached ArchiveState
	if err := json.Unmarshal(raw, &detached); err != nil {
		return err
	}
	if err := verify(detached); err != nil {
		return err
	}
	m := mutation{Kind: kArchiveReady, Project: t.project, ArchiveGeneration: s.Generation}
	if err := t.d.persist(m); err != nil {
		return err
	}
	return t.d.apply(registry.Principal{Kind: registry.Operator}, m)
}

func (t *ArchiveTransaction) Cancel(verify func(ArchiveOperation) error, processed func() error) error {
	if err := t.ready(); err != nil {
		return err
	}
	if verify == nil || processed == nil {
		return ErrBlocked
	}
	state := t.d.archiveStates[t.project]
	op := state.Pending
	if op == nil {
		if state.LastCommitted {
			return ErrBlocked
		}
		op = state.Last
	}
	if op == nil {
		return ErrBlocked
	}
	if err := t.d.budget.Resume(operationEvidence(op)); err != nil {
		return err
	}
	raw, _ := json.Marshal(op)
	var detached ArchiveOperation
	if err := json.Unmarshal(raw, &detached); err != nil {
		return err
	}
	if err := verify(detached); err != nil {
		return err
	}
	if state.Pending != nil {
		if err := t.persistPhase(kArchiveCancel, op); err != nil {
			return err
		}
	}
	if err := processed(); err != nil {
		return err
	}
	return t.d.budget.Finish()
}

// RecoverUnreservedArchiveIntent releases only a clean pre-reservation crash.
// An external phase cannot start before its accepted reserve receipt.
func (d *Durable) RecoverUnreservedArchiveIntent(actor registry.Principal) error {
	d.mu.Lock()
	defer d.mu.Unlock()
	if err := d.ready(); err != nil {
		return err
	}
	if actor.Kind != registry.Operator {
		return registry.ErrNotOperator
	}
	if d.budget == nil {
		return budget.ErrBlocked
	}
	pending := d.budget.Snapshot().Pending
	if len(pending) == 0 {
		return nil
	}
	if len(pending) != 1 || (pending[0].Evidence.Kind != "archive-source-v2" && pending[0].Evidence.Kind != "archive-index-v2") {
		return budget.ErrBlocked
	}
	recs, report, err := wal.Accepted(filepath.Join(d.stateDir, "wal"))
	if err != nil {
		return err
	}
	if report.IsBlocked() || report.TruncateAt >= 0 {
		return budget.ErrBlocked
	}
	for _, r := range recs {
		var m mutation
		if err := json.Unmarshal(r.Payload, &m); err != nil {
			return err
		}
		if m.ArchiveProjection != nil && projectionEvidence(*m.ArchiveProjection) == pending[0].Evidence {
			return budget.ErrBlocked
		}
		if m.ArchiveOperation != nil && operationEvidence(m.ArchiveOperation) == pending[0].Evidence {
			return budget.ErrBlocked
		}
	}
	return d.budget.Recover(func(i budget.Intent) (bool, error) { return i.Evidence == pending[0].Evidence, nil })
}

// WithArchiveWriter selects the legacy/metadata path under the SAME authority
// lock as mutation. The callback must not call locking Durable methods. A nil tx
// means the project has never activated metadata; it is not a fallback after failure.
func (d *Durable) WithArchiveWriter(actor registry.Principal, project string, action func(*ArchiveTransaction) error) error {
	d.mu.Lock()
	defer d.mu.Unlock()
	defer func() { d.externalActive = false }()
	if err := d.ready(); err != nil {
		return err
	}
	if actor.Kind != registry.Operator {
		return registry.ErrNotOperator
	}
	if !d.reg.HasProject(project) {
		return registry.ErrUnknownProj
	}
	if action == nil {
		return errors.New("control: missing archive writer")
	}
	if _, ok := d.archiveStates[project]; !ok {
		return action(nil)
	}
	if d.budget == nil {
		return budget.ErrBlocked
	}
	tx := &ArchiveTransaction{d: d, project: project, active: true}
	defer func() { tx.active = false }()
	return action(tx)
}
func (t *ArchiveTransaction) State() (ArchiveState, error) {
	if err := t.ready(); err != nil {
		return ArchiveState{}, err
	}
	raw, err := json.Marshal(t.d.archiveStates[t.project])
	if err != nil {
		return ArchiveState{}, err
	}
	var state ArchiveState
	err = json.Unmarshal(raw, &state)
	return state, err
}

// RecoveryOperation returns only this project's operation owning the surviving
// ledger intent. Completed historical receipts are not pending work. It must be
// called under the transaction fence, and returns detached evidence.
func (t *ArchiveTransaction) RecoveryOperation() (*ArchiveOperation, string, error) {
	if err := t.ready(); err != nil {
		return nil, "", err
	}
	state, err := t.State()
	if err != nil {
		return nil, "", err
	}
	pending := t.d.budget.Snapshot().Pending
	if len(pending) == 0 {
		if state.Pending != nil {
			return nil, "", budget.ErrBlocked
		}
		return nil, "", nil
	}
	if len(pending) != 1 {
		return nil, "", budget.ErrBlocked
	}
	op := state.Pending
	phase := "reserved"
	if op == nil {
		op = state.Last
		phase = "cancelled"
		if state.LastCommitted {
			phase = "committed"
		}
	}
	if op == nil || operationEvidence(op) != pending[0].Evidence {
		if state.Pending != nil {
			return nil, "", budget.ErrBlocked
		}
		return nil, "", nil
	}
	if err := t.d.budget.Resume(operationEvidence(op)); err != nil {
		return nil, "", err
	}
	return op, phase, nil
}

func (t *ArchiveTransaction) Project() (string, error) {
	if err := t.ready(); err != nil {
		return "", err
	}
	return t.project, nil
}
