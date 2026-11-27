package workflow

import (
	"aifactory.local/storage/internal/logical"
	"context"
	"encoding/json"
	"fmt"

	"github.com/jackc/pgx/v5"
)

// SchemaLogicalBytes charges all embedded schema/index definitions and their
// version registry representations up front, before any startup DDL is allowed.
func SchemaLogicalBytes() int64 {
	entries, e := migrationFS.ReadDir("migrations")
	if e != nil {
		panic(e)
	}
	total := int64(len(`logical-v1:schema_migrations(name,applied_at);primary(name);derived_index_version(true,1);primary(true)`))
	for _, entry := range entries {
		if entry.IsDir() {
			continue
		}
		b, e := migrationFS.ReadFile("migrations/" + entry.Name())
		if e != nil {
			panic(e)
		}
		total += int64(len(b) + len(entry.Name())*2 + 64)
	}
	return total
}

// managedTables lists every relation the logical inventory bills, in billing order.
var managedTables = []string{"schema_migrations", "workflow_tasks", "archive_index", "document_index", "archive_checkpoint"}

// tableColumns is the billed select list of one managed table.
func tableColumns(table string, metadataSchema bool) string {
	switch table {
	case "schema_migrations":
		return `name`
	case "workflow_tasks":
		return `project,id,version,fields`
	case "archive_index":
		if metadataSchema {
			return `key_hash,project_hash,project,identity,payload_hash,terms::text,tsvector_to_array(terms),metadata_hash,source_generation,source_ordinal,captured_key,source_time_key`
		}
		return `key_hash,project_hash,project,identity,payload_hash,terms::text,tsvector_to_array(terms)`
	case "archive_checkpoint":
		return `project_hash,project,source_generation,projection_generation,policy_revision,ordinal,complete`
	case "document_index":
		return `key_hash,project_hash,project,identity,data`
	}
	panic("workflow: unmanaged table " + table)
}

// rowCost bills one row read with tableColumns; scan fills the billed columns.
// It keeps every refusal of the full inventory: unknown migrations, malformed
// task fields and inconsistent metadata rows fail instead of being skipped.
func rowCost(table string, metadataSchema bool, scan func(...any) error) (int64, error) {
	switch table {
	case "schema_migrations":
		var name string
		if e := scan(&name); e != nil {
			return 0, e
		}
		if _, e := migrationFS.ReadFile("migrations/" + name); e != nil {
			return 0, ErrSchemaNewerThanImage
		}
		return 0, nil
	case "workflow_tasks":
		var project, id string
		var version int64
		var raw []byte
		var fields map[string]string
		if e := scan(&project, &id, &version, &raw); e != nil {
			return 0, e
		}
		if e := json.Unmarshal(raw, &fields); e != nil {
			return 0, e
		}
		return logical.Workflow(project, id, version, fields), nil
	case "archive_index":
		var key, ph, project, identity, payload, terms string
		var lexemes []string
		var metadataHash, generation, captured, event *string
		var ordinal *int64
		var e error
		if metadataSchema {
			e = scan(&key, &ph, &project, &identity, &payload, &terms, &lexemes, &metadataHash, &generation, &ordinal, &captured, &event)
		} else {
			e = scan(&key, &ph, &project, &identity, &payload, &terms, &lexemes)
		}
		if e != nil {
			return 0, e
		}
		cost := logical.ArchiveIndex(key, ph, project, identity, payload, terms, lexemes)
		if metadataHash != nil {
			if generation == nil || ordinal == nil || *ordinal <= 0 {
				return 0, fmt.Errorf("workflow: invalid metadata inventory")
			}
			cost += logical.ArchiveMetadata(key, ph, project, *generation, *metadataHash, *ordinal, captured, event)
		} else if generation != nil || ordinal != nil || captured != nil || event != nil {
			return 0, fmt.Errorf("workflow: unversioned metadata inventory")
		}
		return cost, nil
	case "archive_checkpoint":
		var ph, project, source, projection, policy string
		var ordinal int64
		var complete bool
		if e := scan(&ph, &project, &source, &projection, &policy, &ordinal, &complete); e != nil {
			return 0, e
		}
		return logical.ArchiveCheckpoint(ph, project, source, projection, policy, ordinal, complete), nil
	case "document_index":
		var key, ph, project, identity string
		var raw []byte
		if e := scan(&key, &ph, &project, &identity, &raw); e != nil {
			return 0, e
		}
		return logical.DocumentIndex(key, ph, project, identity, raw)
	}
	return 0, fmt.Errorf("workflow: unmanaged table %s", table)
}

// querier is the read surface shared by the pool and a snapshot transaction.
type querier interface {
	Query(ctx context.Context, sql string, args ...any) (pgx.Rows, error)
	QueryRow(ctx context.Context, sql string, args ...any) pgx.Row
}

// managedLayout reports which managed tables exist and whether the metadata schema is present.
func managedLayout(ctx context.Context, q querier) (map[string]bool, bool, error) {
	var metadataSchema bool
	if e := q.QueryRow(ctx, `SELECT to_regclass('archive_checkpoint') IS NOT NULL`).Scan(&metadataSchema); e != nil {
		return nil, false, e
	}
	exists := map[string]bool{}
	for _, table := range managedTables {
		var ok bool
		if e := q.QueryRow(ctx, `SELECT to_regclass($1) IS NOT NULL`, table).Scan(&ok); e != nil {
			return nil, false, e
		}
		exists[table] = ok
	}
	return exists, metadataSchema, nil
}

// LogicalBytes reads only managed relations, including all declared index
// representations. It works before initial migration and never performs DDL.
func (s *PGStore) LogicalBytes(ctx context.Context, limit int64) (int64, error) {
	ctx, cancel := context.WithTimeout(ctx, InventoryTimeout)
	defer cancel()
	total := SchemaLogicalBytes()
	if total > limit {
		return 0, fmt.Errorf("workflow: logical inventory exceeds cap")
	}
	exists, metadataSchema, e := managedLayout(ctx, s.pool)
	if e != nil {
		return 0, e
	}
	for _, table := range managedTables {
		if !exists[table] {
			continue
		}
		rows, e := s.pool.Query(ctx, `SELECT `+tableColumns(table, metadataSchema)+` FROM `+table)
		if e != nil {
			return 0, e
		}
		for rows.Next() {
			cost, e := rowCost(table, metadataSchema, rows.Scan)
			if e == nil {
				total, e = logical.Add(total, cost, limit)
			}
			if e != nil {
				rows.Close()
				return 0, e
			}
		}
		e = rows.Err()
		rows.Close()
		if e != nil {
			return 0, e
		}
	}
	return total, nil
}

// ProveArchiveIndex checks one exact derived write; absence is not success.
func (s *PGStore) ProveArchiveIndex(ctx context.Context, key, payload string) (bool, error) {
	var found bool
	e := s.pool.QueryRow(ctx, `SELECT EXISTS(SELECT 1 FROM archive_index WHERE key_hash=$1 AND payload_hash=$2)`, key, payload).Scan(&found)
	return found, e
}
