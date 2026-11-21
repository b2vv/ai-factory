package workflow

import (
	"context"
	"encoding/json"
	"fmt"
	"github.com/jackc/pgx/v5"
)

// RollbackInitial applies only the reviewed inverse of 0001_workflow.sql. The
// trusted maintenance coordinator must hold current control authority and verify
// the locked actual rows. There is no generic arbitrary-SQL/down-migration path.
func (s *PGStore) RollbackInitial(ctx context.Context, verify func(map[string][]Task) error) error {
	return s.RollbackInitialWithIndex(ctx, verify, nil)
}
func (s *PGStore) RollbackInitialWithIndex(ctx context.Context, verify func(map[string][]Task) error, verifyIndex func([]DerivedIndexRecord, []DerivedDocumentRecord) error) error {
	if verify == nil {
		return fmt.Errorf("workflow: rollback verification required")
	}
	ctx, cancel := context.WithTimeout(ctx, s.opTimeout)
	defer cancel()
	tx, e := s.pool.BeginTx(ctx, pgx.TxOptions{IsoLevel: pgx.Serializable})
	if e != nil {
		return e
	}
	defer tx.Rollback(ctx)
	if _, e = tx.Exec(ctx, `LOCK TABLE schema_migrations IN ACCESS EXCLUSIVE MODE`); e != nil {
		return e
	}
	rows, e := tx.Query(ctx, `SELECT name FROM schema_migrations ORDER BY name`)
	if e != nil {
		return e
	}
	names := []string{}
	for rows.Next() {
		var n string
		if e = rows.Scan(&n); e != nil {
			rows.Close()
			return e
		}
		names = append(names, n)
	}
	rows.Close()
	if e = rows.Err(); e != nil {
		return e
	}
	withIndex := len(names) == 2 && names[0] == "0001_workflow.sql" && names[1] == "0002_derived_index.sql"
	if !withIndex && (len(names) != 1 || names[0] != "0001_workflow.sql") {
		return fmt.Errorf("workflow: rollback supports reviewed workflow and derived-index migrations only; refusing unknown state")
	}
	if withIndex {
		if e = verifyDerivedIndex(ctx, tx, verifyIndex); e != nil {
			return e
		}
	}
	if _, e = tx.Exec(ctx, `LOCK TABLE workflow_tasks IN ACCESS EXCLUSIVE MODE`); e != nil {
		return e
	}
	columns, e := tx.Query(ctx, `SELECT attname,format_type(atttypid,atttypmod),attnotnull FROM pg_attribute WHERE attrelid='workflow_tasks'::regclass AND attnum>0 AND NOT attisdropped ORDER BY attnum`)
	if e != nil {
		return e
	}
	expected := [][2]string{{"project", "text"}, {"id", "text"}, {"version", "bigint"}, {"fields", "jsonb"}}
	position := 0
	for columns.Next() {
		var name, kind string
		var required bool
		if e = columns.Scan(&name, &kind, &required); e != nil {
			columns.Close()
			return e
		}
		if position >= len(expected) || expected[position] != [2]string{name, kind} || !required {
			columns.Close()
			return fmt.Errorf("workflow: table shape differs from reviewed migration")
		}
		position++
	}
	columns.Close()
	if e = columns.Err(); e != nil {
		return e
	}
	if position != len(expected) {
		return fmt.Errorf("workflow: unexpected table shape")
	}
	rows, e = tx.Query(ctx, `SELECT project,id,version,fields FROM workflow_tasks ORDER BY project,id`)
	if e != nil {
		return e
	}
	data := map[string][]Task{}
	used := 0
	for rows.Next() {
		var project string
		var t Task
		var raw []byte
		if e = rows.Scan(&project, &t.ID, &t.Version, &raw); e != nil {
			rows.Close()
			return e
		}
		used += len(project) + len(t.ID) + len(raw) + 32
		if used > MaxSnapshotBytes*4 {
			rows.Close()
			return fmt.Errorf("workflow: rollback verification bound exceeded")
		}
		if e = json.Unmarshal(raw, &t.Fields); e != nil {
			rows.Close()
			return e
		}
		data[project] = append(data[project], t)
	}
	rows.Close()
	if e = rows.Err(); e != nil {
		return e
	}
	if e = verify(data); e != nil {
		return e
	}
	if withIndex {
		down, e := migrationFS.ReadFile("migrations/down/0002_derived_index.sql")
		if e != nil {
			return e
		}
		if _, e = tx.Exec(ctx, string(down)); e != nil {
			return e
		}
		if _, e = tx.Exec(ctx, `DELETE FROM schema_migrations WHERE name='0002_derived_index.sql'`); e != nil {
			return e
		}
	}
	sql, e := migrationFS.ReadFile("migrations/down/0001_workflow.sql")
	if e != nil {
		return e
	}
	if _, e = tx.Exec(ctx, string(sql)); e != nil {
		return e
	}
	if _, e = tx.Exec(ctx, `DELETE FROM schema_migrations WHERE name='0001_workflow.sql'`); e != nil {
		return e
	}
	return tx.Commit(ctx)
}
