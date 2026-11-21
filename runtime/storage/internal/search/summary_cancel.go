package search

import (
	"aifactory.local/storage/internal/control"
	"context"
)

// cancelProjection resumes only an owned retained operation. Its durable witness
// precedes SQL cleanup; errors and readback uncertainty preserve the same intent.
func (s *Store) cancelProjection(tx *control.ArchiveTransaction, p control.ArchiveProjection) error {
	if err := tx.BeginProjectionCancellation(p); err != nil {
		return err
	}
	if s.schemaVersion != 2 {
		return ErrCheckpoint
	}
	ctx, cancel := context.WithTimeout(context.Background(), s.timeout)
	defer cancel()
	sqlTx, err := s.pool.Begin(ctx)
	if err != nil {
		return err
	}
	defer sqlTx.Rollback(ctx)
	project := p.Desired.Project
	if _, err = sqlTx.Exec(ctx, `DELETE FROM archive_index WHERE project_hash=$1 AND project=$2`, hash(project), project); err != nil {
		return err
	}
	if _, err = sqlTx.Exec(ctx, `DELETE FROM archive_checkpoint WHERE project_hash=$1 AND project=$2`, hash(project), project); err != nil {
		return err
	}
	if err = sqlTx.Commit(ctx); err != nil {
		return err
	}
	return tx.FinishCancelledProjection(p, func() error {
		proofCtx, proofCancel := context.WithTimeout(context.Background(), s.timeout)
		defer proofCancel()
		var rowsEmpty, checkpointEmpty bool
		err := s.pool.QueryRow(proofCtx, `SELECT NOT EXISTS(SELECT 1 FROM archive_index WHERE project_hash=$1 AND project=$2), NOT EXISTS(SELECT 1 FROM archive_checkpoint WHERE project_hash=$1 AND project=$2)`, hash(project), project).Scan(&rowsEmpty, &checkpointEmpty)
		if err != nil {
			return err
		}
		if !rowsEmpty || !checkpointEmpty {
			return ErrCheckpoint
		}
		return nil
	})
}
