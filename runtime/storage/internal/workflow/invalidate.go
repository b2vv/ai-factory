package workflow

import "context"

// InvalidateDerived removes only this project's rebuildable projections before
// restore. It does not alter source files, workflow ownership or control grants.
func (s *PGStore) InvalidateDerived(project string) error {
	ctx, cancel := context.WithTimeout(context.Background(), s.opTimeout)
	defer cancel()
	tx, e := s.pool.Begin(ctx)
	if e != nil {
		return e
	}
	defer tx.Rollback(ctx)
	for _, table := range []string{"archive_index", "document_index"} {
		if _, e = tx.Exec(ctx, "DELETE FROM "+table+" WHERE project=$1", project); e != nil {
			return e
		}
	}
	return tx.Commit(ctx)
}
