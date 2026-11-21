package workflow

import (
	"context"
	"fmt"
)

const ArchiveMetadataMigration = "0003_archive_metadata.sql"
const DefaultSchemaVersion = 2

// UpgradeArchiveMetadata is an exclusive offline coordinator operation. The
// caller must hold control ownership, persist activation and admit schema cost
// before calling. Ordinary OpenPostgres deliberately never applies this step.
func (s *PGStore) UpgradeArchiveMetadata(ctx context.Context) error {
	ctx, cancel := context.WithTimeout(ctx, 30*s.opTimeout)
	defer cancel()
	tx, err := s.pool.Begin(ctx)
	if err != nil {
		return err
	}
	defer tx.Rollback(ctx)
	if _, err := tx.Exec(ctx, `SELECT pg_advisory_xact_lock(170113,0)`); err != nil {
		return err
	}
	if _, err := tx.Exec(ctx, `LOCK TABLE schema_migrations IN SHARE ROW EXCLUSIVE MODE`); err != nil {
		return err
	}
	rows, err := tx.Query(ctx, `SELECT name FROM schema_migrations ORDER BY name`)
	if err != nil {
		return err
	}
	names := []string{}
	for rows.Next() {
		var name string
		if err := rows.Scan(&name); err != nil {
			rows.Close()
			return err
		}
		names = append(names, name)
	}
	rows.Close()
	if err := rows.Err(); err != nil {
		return err
	}
	expected := []string{"0001_workflow.sql", "0002_derived_index.sql", ArchiveMetadataMigration}
	if len(names) < 2 || len(names) > 3 {
		return fmt.Errorf("%w: unexpected metadata upgrade baseline", ErrSchemaNewerThanImage)
	}
	for n, name := range names {
		if name != expected[n] {
			return fmt.Errorf("%w: unexpected metadata upgrade migration", ErrSchemaNewerThanImage)
		}
	}
	var version int
	if err := tx.QueryRow(ctx, `SELECT version FROM derived_index_version WHERE singleton=true`).Scan(&version); err != nil {
		return err
	}
	if len(names) == 3 {
		if version != 2 {
			return fmt.Errorf("workflow: inconsistent metadata schema version")
		}
		return tx.Commit(ctx)
	}
	if version != 1 {
		return fmt.Errorf("workflow: inconsistent legacy index schema")
	}
	sql, err := migrationFS.ReadFile("migrations/" + ArchiveMetadataMigration)
	if err != nil {
		return err
	}
	if _, err := tx.Exec(ctx, string(sql)); err != nil {
		return err
	}
	if _, err := tx.Exec(ctx, `INSERT INTO schema_migrations(name) VALUES($1)`, ArchiveMetadataMigration); err != nil {
		return err
	}
	return tx.Commit(ctx)
}

// ArchiveMetadataReady is a read-only check for migration retry ordering.
func (s *PGStore) ArchiveMetadataReady(ctx context.Context) (bool, error) {
	ctx, cancel := context.WithTimeout(ctx, s.opTimeout)
	defer cancel()
	var applied bool
	var version int
	err := s.pool.QueryRow(ctx, `SELECT EXISTS(SELECT 1 FROM schema_migrations WHERE name=$1),version FROM derived_index_version WHERE singleton=true`, ArchiveMetadataMigration).Scan(&applied, &version)
	if err != nil {
		return false, err
	}
	if applied != (version == 2) {
		return false, fmt.Errorf("workflow: inconsistent metadata schema")
	}
	return applied, nil
}
