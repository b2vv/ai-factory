package workflow

import (
	"context"
	"fmt"

	"aifactory.local/storage/internal/logical"
	"github.com/jackc/pgx/v5"
)

// tableKey is each managed table's primary key as text.
func tableKey(table string) string {
	switch table {
	case "schema_migrations":
		return `name`
	case "workflow_tasks":
		return `json_build_array(project,id)::text`
	case "archive_index", "document_index":
		return `key_hash`
	case "archive_checkpoint":
		return `project_hash`
	}
	panic("workflow: unmanaged table " + table)
}

type rowState struct {
	version string // the row's xmin: every change of the row writes a new tuple version
	cost    int64
}

// Inventory is a logical inventory remembered per row, so a later pass only
// rereads rows whose tuple version changed. Its Total always equals what
// LogicalBytes returns for the same snapshot.
type Inventory struct {
	Total          int64
	exists         map[string]bool
	metadataSchema bool
	rows           map[string]map[string]rowState
}

// Inventory builds (prev == nil) or refreshes the per-row logical inventory in one
// REPEATABLE READ READ ONLY snapshot. A changed table set or metadata schema rebuilds
// it; any error returns no inventory, so the caller cannot keep a half-merged one.
func (s *PGStore) Inventory(ctx context.Context, limit int64, prev *Inventory) (*Inventory, error) {
	ctx, cancel := context.WithTimeout(ctx, s.opTimeout)
	defer cancel()
	tx, e := s.pool.BeginTx(ctx, pgx.TxOptions{IsoLevel: pgx.RepeatableRead, AccessMode: pgx.ReadOnly})
	if e != nil {
		return nil, e
	}
	defer tx.Rollback(ctx)
	exists, metadataSchema, e := managedLayout(ctx, tx)
	if e != nil {
		return nil, e
	}
	if prev != nil && (prev.metadataSchema != metadataSchema || !sameTables(prev.exists, exists)) {
		prev = nil
	}
	next := &Inventory{exists: exists, metadataSchema: metadataSchema, rows: map[string]map[string]rowState{}}
	total := SchemaLogicalBytes()
	if total > limit {
		return nil, fmt.Errorf("workflow: logical inventory exceeds cap")
	}
	for _, table := range managedTables {
		if !exists[table] {
			continue
		}
		var old map[string]rowState
		if prev != nil {
			old = prev.rows[table]
		}
		rows, e := s.tableInventory(ctx, tx, table, metadataSchema, old)
		if e != nil {
			return nil, e
		}
		for _, r := range rows {
			if r.cost < 0 {
				return nil, fmt.Errorf("workflow: negative logical cost")
			}
			if total, e = logical.Add(total, r.cost, limit); e != nil {
				return nil, e
			}
		}
		next.rows[table] = rows
	}
	if e = tx.Commit(ctx); e != nil {
		return nil, e
	}
	next.Total = total
	return next, nil
}

func sameTables(a, b map[string]bool) bool {
	if len(a) != len(b) {
		return false
	}
	for k, v := range a {
		if b[k] != v {
			return false
		}
	}
	return true
}

// tableInventory lists every row's key and version, keeps the cost of rows whose
// version is unchanged and bills the rest from a reread inside the same snapshot.
func (s *PGStore) tableInventory(ctx context.Context, tx pgx.Tx, table string, metadataSchema bool, old map[string]rowState) (map[string]rowState, error) {
	key := tableKey(table)
	cols := tableColumns(table, metadataSchema)
	result := map[string]rowState{}
	if old == nil {
		rows, e := tx.Query(ctx, `SELECT `+key+`, xmin::text, `+cols+` FROM `+table)
		if e != nil {
			return nil, e
		}
		defer rows.Close()
		for rows.Next() {
			var k, version string
			cost, e := rowCost(table, metadataSchema, func(dest ...any) error {
				return rows.Scan(append([]any{&k, &version}, dest...)...)
			})
			if e != nil {
				return nil, e
			}
			result[k] = rowState{version: version, cost: cost}
		}
		return result, rows.Err()
	}
	var stale []string
	rows, e := tx.Query(ctx, `SELECT `+key+`, xmin::text FROM `+table)
	if e != nil {
		return nil, e
	}
	for rows.Next() {
		var k, version string
		if e = rows.Scan(&k, &version); e != nil {
			rows.Close()
			return nil, e
		}
		if was, ok := old[k]; ok && was.version == version {
			result[k] = was
		} else {
			stale = append(stale, k)
		}
	}
	e = rows.Err()
	rows.Close()
	if e != nil {
		return nil, e
	}
	if len(stale) == 0 {
		return result, nil
	}
	reread, e := tx.Query(ctx, `SELECT `+key+`, xmin::text, `+cols+` FROM `+table+` WHERE `+key+` = ANY($1)`, stale)
	if e != nil {
		return nil, e
	}
	defer reread.Close()
	for reread.Next() {
		var k, version string
		cost, e := rowCost(table, metadataSchema, func(dest ...any) error {
			return reread.Scan(append([]any{&k, &version}, dest...)...)
		})
		if e != nil {
			return nil, e
		}
		result[k] = rowState{version: version, cost: cost}
	}
	if e = reread.Err(); e != nil {
		return nil, e
	}
	for _, k := range stale {
		if _, ok := result[k]; !ok {
			return nil, fmt.Errorf("workflow: row vanished inside one snapshot")
		}
	}
	return result, nil
}
