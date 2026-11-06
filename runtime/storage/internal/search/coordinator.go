package search

import (
	"aifactory.local/storage/internal/archive"
	"aifactory.local/storage/internal/control"
	"crypto/rand"
	"encoding/hex"
	"strconv"
)

type MetadataSource interface {
	archive.MetadataStore
	ScanEnvelopes(string, string, int64, int64) (archive.EnvelopeWindow, error)
}

func envelopeDigest(e archive.Envelope) (string, error) {
	raw, err := archive.EncodeEnvelope(e)
	if err != nil {
		return "", err
	}
	return hash(string(raw)), nil
}

// RecoverProjection consumes the durable operation's original generation token.
// The caller holds the control writer fence, including the current policy gate.
func (s *Store) RecoverProjection(tx *control.ArchiveTransaction, source MetadataSource, gate func(archive.Record) bool) error {
	if tx == nil || source == nil || gate == nil {
		return ErrCheckpoint
	}
	op, err := tx.RecoveryProjection()
	if err != nil || op == nil {
		return err
	}
	return s.applyProjection(tx, source, gate, *op, 0)
}
func (s *Store) applyProjection(tx *control.ArchiveTransaction, source MetadataSource, gate func(archive.Record) bool, op control.ArchiveProjection, cost int64) error {
	var e archive.Envelope
	if op.Action == "project" {
		actual, found, err := source.LookupEnvelope(op.Identity)
		if err != nil {
			return err
		}
		if !found || !gate(actual.Record) {
			return ErrCheckpoint
		}
		digest, err := envelopeDigest(actual)
		if err != nil {
			return err
		}
		if digest != op.EnvelopeHash {
			return archive.ErrIDConflict
		}
		e = actual
	}
	if err := tx.ReserveProjection(op, cost); err != nil {
		return err
	}
	var writeErr error
	switch op.Action {
	case "rebuild":
		writeErr = s.BeginRebuild(op.Desired, op.Expected.ProjectionGeneration)
	case "project":
		writeErr = s.PutEnvelope(e, op.Expected)
	case "advance":
		writeErr = s.AdvanceCheckpoint(op.Expected, op.Desired.Ordinal)
	case "complete":
		writeErr = s.CompleteCheckpoint(op.Expected, op.Desired.Ordinal)
	default:
		return ErrCheckpoint
	}
	return tx.FinishProjection(op, func() error {
		checkpoint, found, err := s.Checkpoint(op.Desired.Project)
		if err != nil {
			return err
		}
		if !found || checkpoint != op.Desired {
			if writeErr != nil {
				return writeErr
			}
			return ErrCheckpoint
		}
		if op.Action == "rebuild" {
			match, err := s.MatchesEmptyRebuild(op.Desired)
			if err != nil {
				return err
			}
			if !match {
				return ErrCheckpoint
			}
		}
		if op.Action == "project" {
			match, err := s.MatchesEnvelope(e, op.Desired)
			if err != nil {
				return err
			}
			if !match {
				return ErrCheckpoint
			}
		}
		return nil
	})
}

// ProjectArchive inspects at most one bounded source page. Hidden-only pages
// advance an incomplete checkpoint, and exhaustion alone permits completion.
// No source timestamp, latest hit or row count is a completeness proof.
func (s *Store) ProjectArchive(tx *control.ArchiveTransaction, source MetadataSource, gate func(archive.Record) bool) (int, error) {
	if tx == nil || source == nil || gate == nil {
		return 0, ErrCheckpoint
	}
	if err := s.RecoverProjection(tx, source, gate); err != nil {
		return 0, err
	}
	state, err := tx.State()
	if err != nil {
		return 0, err
	}
	project, err := tx.Project()
	if err != nil {
		return 0, err
	}
	if state.Pending != nil {
		return 0, ErrCheckpoint
	}
	current, found, err := s.Checkpoint(project)
	if err != nil {
		return 0, err
	}
	policy := strconv.FormatUint(state.PolicyRevision, 10)
	if !found || current.SourceGeneration != state.Generation || current.PolicyRevision != policy {
		token := make([]byte, 32)
		if _, err := rand.Read(token); err != nil {
			return 0, err
		}
		desired := Checkpoint{Project: project, SourceGeneration: state.Generation, ProjectionGeneration: hex.EncodeToString(token), PolicyRevision: policy}
		plan := control.ArchiveProjection{Action: "rebuild", Expected: current, Desired: desired}
		cost, err := s.CheckpointReservationBytes(desired)
		if err != nil {
			return 0, err
		}
		if err := s.applyProjection(tx, source, gate, plan, cost); err != nil {
			return 0, err
		}
		current = desired
	}
	if current.Ordinal > state.CommittedOrdinal {
		return 0, ErrCheckpoint
	}
	if current.Complete && current.Ordinal == state.CommittedOrdinal {
		return 0, nil
	}
	window, err := source.ScanEnvelopes(project, state.Generation, current.Ordinal, state.CommittedOrdinal)
	if err != nil {
		return 0, err
	}
	if len(window.Records) == 0 && window.More {
		return 0, ErrCheckpoint
	}
	last := current.Ordinal
	for n, e := range window.Records {
		if e.Record.Project != project || e.Metadata.Generation != state.Generation || e.Metadata.Ordinal <= last || e.Metadata.Ordinal > state.CommittedOrdinal {
			return n, ErrCheckpoint
		}
		last = e.Metadata.Ordinal
		if !gate(e.Record) {
			continue
		}
		desired := current
		desired.Ordinal = e.Metadata.Ordinal
		desired.Complete = false
		digest, err := envelopeDigest(e)
		if err != nil {
			return n, err
		}
		identity := archive.Record{Project: e.Record.Project, SourceInstance: e.Record.SourceInstance, SessionID: e.Record.SessionID, MessageID: e.Record.MessageID}
		plan := control.ArchiveProjection{Action: "project", Expected: current, Desired: desired, Identity: identity, EnvelopeHash: digest}
		cost, err := s.ProjectionReservationBytes(e, current)
		if err != nil {
			return n, err
		}
		if err := s.applyProjection(tx, source, gate, plan, cost); err != nil {
			return n, err
		}
		current = desired
	}
	desired := current
	action := "advance"
	desired.Ordinal = last
	desired.Complete = false
	if !window.More {
		action = "complete"
		desired.Ordinal = state.CommittedOrdinal
		desired.Complete = true
	}
	if desired != current {
		cost, err := s.CheckpointReservationBytes(desired)
		if err != nil {
			return len(window.Records), err
		}
		if err := s.applyProjection(tx, source, gate, control.ArchiveProjection{Action: action, Expected: current, Desired: desired}, cost); err != nil {
			return len(window.Records), err
		}
	}
	return len(window.Records), nil
}
