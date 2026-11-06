package ingest

import (
	"aifactory.local/storage/internal/archive"
	"aifactory.local/storage/internal/control"
	"aifactory.local/storage/internal/wal"
	"bytes"
	"crypto/sha256"
	"encoding/hex"
	"errors"
)

// CommitEnvelope runs the intake/source portion of an already reserved operation.
// The caller holds the control writer fence and has checked the publish gate.
// Acceptance, exact source verification, control commitment and processing occur
// in that order. Only control releases the shared budget intent.
func (i *Ingestor) CommitEnvelope(tx *control.ArchiveTransaction, e archive.Envelope) (wal.Receipt, error) {
	if tx == nil {
		return wal.Receipt{}, ErrMetadataTransaction
	}
	state, err := tx.State()
	if err != nil {
		return wal.Receipt{}, err
	}
	if !state.MigrationComplete || e.Metadata.Generation != state.Generation {
		return wal.Receipt{}, ErrMetadataTransaction
	}
	source, ok := i.store.(archive.MetadataStore)
	if !ok {
		return wal.Receipt{}, ErrMetadataTransaction
	}
	receipt, err := i.AcceptEnvelope(e)
	if err != nil {
		return receipt, err
	}
	writeErr := source.PutEnvelope(e)
	verify := func(expected archive.Envelope) error {
		actual, found, err := source.LookupEnvelope(expected.Record)
		if err != nil {
			return err
		}
		if !found {
			if writeErr != nil {
				return writeErr
			}
			return errors.New("ingest: source projection missing")
		}
		want, err := archive.EncodeEnvelope(expected)
		if err != nil {
			return err
		}
		got, err := archive.EncodeEnvelope(actual)
		if err != nil {
			return err
		}
		if !bytes.Equal(want, got) {
			return archive.ErrIDConflict
		}
		return nil
	}
	// An uncertain insert may have succeeded. Exact readback is the proof, never
	// an error string or an ordinal alone.
	err = tx.Complete(e.Record, verify, func() error { return i.MarkEnvelopeProcessed(e) })
	return receipt, err
}

// RecoverEnvelope reconciles only the operation selected by control's exact
// surviving intent. Callers hold the writer fence and provide a monotone policy
// gate; unknown authority must fail before this method is called.
func (i *Ingestor) RecoverEnvelope(tx *control.ArchiveTransaction, gate func(archive.Record) bool) error {
	if tx == nil || gate == nil {
		return ErrMetadataTransaction
	}
	op, phase, err := tx.RecoveryOperation()
	if err != nil || op == nil {
		return err
	}
	if op.Metadata.Legacy {
		return ErrMetadataTransaction
	} // offline migration owns historical attachment
	e, found, err := i.AcceptedEnvelope(op.Identity)
	if err != nil {
		return err
	}
	source, ok := i.store.(archive.MetadataStore)
	if !ok {
		return ErrMetadataTransaction
	}
	if !found {
		if phase == "committed" {
			return ErrMetadataTransaction
		}
		return tx.Cancel(func(control.ArchiveOperation) error {
			_, found, err := source.LookupEnvelope(op.Identity)
			if err != nil {
				return err
			}
			if found {
				return ErrMetadataTransaction
			}
			return nil
		}, func() error { return nil })
	}
	raw, err := archive.EncodeEnvelope(e)
	if err != nil {
		return err
	}
	hash := sha256.Sum256(raw)
	if hex.EncodeToString(hash[:]) != op.EnvelopeHash {
		return archive.ErrIDConflict
	}
	if phase == "cancelled" || phase == "reserved" && !gate(e.Record) {
		return tx.Cancel(func(control.ArchiveOperation) error { return nil }, func() error { return i.MarkEnvelopeProcessed(e) })
	}
	// A committed source is verified again before its processing marker. Never
	// recreate a disappeared committed record from WAL during recovery.
	if phase == "committed" {
		return tx.Complete(e.Record, func(expected archive.Envelope) error {
			got, found, err := source.LookupEnvelope(expected.Record)
			if err != nil {
				return err
			}
			if !found {
				return ErrMetadataTransaction
			}
			b, err := archive.EncodeEnvelope(got)
			if err != nil {
				return err
			}
			if !bytes.Equal(raw, b) {
				return archive.ErrIDConflict
			}
			return nil
		}, func() error { return i.MarkEnvelopeProcessed(e) })
	}
	_, err = i.CommitEnvelope(tx, e)
	return err
}
