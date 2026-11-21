package maintenance

import (
	"aifactory.local/storage/internal/archive"
	"aifactory.local/storage/internal/control"
	"bytes"
	"context"
	"errors"
)

type ArchiveMetadataSource interface {
	archive.Store
	archive.MetadataStore
}

// MigrateArchiveSource attaches unknown-time metadata through bounded source
// pages and compare-and-set writes. The offline caller holds exclusive ownership
// and the control writer fence; it must establish schema and the downgrade witness
// first. This does not mark migration COMPLETE: index verification is separate.
func MigrateArchiveSource(ctx context.Context, tx *control.ArchiveTransaction, source ArchiveMetadataSource) error {
	if tx == nil || source == nil {
		return control.ErrBlocked
	}
	state, err := tx.State()
	if err != nil {
		return err
	}
	project, err := tx.Project()
	if err != nil {
		return err
	}
	if state.MigrationComplete {
		return errors.New("maintenance: source migration already completed")
	}
	verify := func(expected archive.Envelope) error {
		got, found, err := source.LookupEnvelope(expected.Record)
		if err != nil {
			return err
		}
		if !found {
			return archive.ErrIDConflict
		}
		a, err := archive.EncodeEnvelope(expected)
		if err != nil {
			return err
		}
		b, err := archive.EncodeEnvelope(got)
		if err != nil {
			return err
		}
		if !bytes.Equal(a, b) {
			return archive.ErrIDConflict
		}
		return nil
	}
	attach := func(r archive.Record) error {
		if err := ctx.Err(); err != nil {
			return err
		}
		e, err := tx.Reserve(r, nil, true)
		if err != nil {
			return err
		}
		writeErr := source.AttachMetadata(e)
		if err := verify(e); err != nil {
			if writeErr != nil {
				return writeErr
			}
			return err
		}
		return tx.Complete(r, verify, func() error { return nil })
	}
	operation, phase, err := tx.RecoveryOperation()
	if err != nil {
		return err
	}
	if operation != nil {
		if !operation.Metadata.Legacy {
			return control.ErrBlocked
		}
		existing, found, err := source.LookupEnvelope(operation.Identity)
		if err != nil {
			return err
		}
		if !found {
			if phase == "committed" {
				return archive.ErrIDConflict
			}
			if err := tx.Cancel(func(control.ArchiveOperation) error { return nil }, func() error { return nil }); err != nil {
				return err
			}
		} else {
			switch phase {
			case "reserved":
				if err := attach(existing.Record); err != nil {
					return err
				}
			case "committed":
				if err := tx.Complete(existing.Record, verify, func() error { return nil }); err != nil {
					return err
				}
			default:
				return archive.ErrIDConflict
			}
		}
	}
	var after *archive.Position
	for {
		if err := ctx.Err(); err != nil {
			return err
		}
		window, err := source.Scan(project, after)
		if err != nil {
			return err
		}
		if len(window.Records) == 0 && window.More {
			return errors.New("maintenance: nonadvancing source page")
		}
		for _, r := range window.Records {
			existing, found, err := source.LookupEnvelope(r)
			if err != nil {
				return err
			}
			if !found || existing.Record != r {
				return archive.ErrIDConflict
			}
			if existing.Version == 1 {
				if err := attach(r); err != nil {
					return err
				}
			} else {
				current, err := tx.State()
				if err != nil {
					return err
				}
				if existing.Metadata.Generation != current.Generation || existing.Metadata.Ordinal > current.CommittedOrdinal {
					return archive.ErrIDConflict
				}
				if _, err := archive.EncodeEnvelope(existing); err != nil {
					return err
				}
			}
			position := archive.PositionOf(r)
			after = &position
		}
		if !window.More {
			return nil
		}
	}
}
