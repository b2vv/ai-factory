package workflow

import (
	"aifactory.local/storage/internal/logical"
	"context"
	"encoding/json"
	"fmt"
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

// LogicalBytes reads only managed relations, including all declared index
// representations. It works before initial migration and never performs DDL.
func (s *PGStore) LogicalBytes(ctx context.Context, limit int64) (int64, error) {
	ctx, cancel := context.WithTimeout(ctx, s.opTimeout)
	defer cancel()
	total := SchemaLogicalBytes()
	if total > limit {
		return 0, fmt.Errorf("workflow: logical inventory exceeds cap")
	}
	for _, table := range []string{"schema_migrations", "workflow_tasks", "archive_index", "document_index"} {
		var exists bool
		if e := s.pool.QueryRow(ctx, `SELECT to_regclass($1) IS NOT NULL`, table).Scan(&exists); e != nil {
			return 0, e
		}
		if !exists {
			continue
		}
		query := ""
		switch table {
		case "schema_migrations":
			query = `SELECT name FROM schema_migrations`
		case "workflow_tasks":
			query = `SELECT project,id,version,fields FROM workflow_tasks`
		case "archive_index":
			query = `SELECT key_hash,project_hash,project,identity,payload_hash,terms::text,tsvector_to_array(terms) FROM archive_index`
		case "document_index":
			query = `SELECT key_hash,project_hash,project,identity,data FROM document_index`
		}
		rows, e := s.pool.Query(ctx, query)
		if e != nil {
			return 0, e
		}
		for rows.Next() {
			var cost int64
			switch table {
			case "schema_migrations":
				var name string
				e = rows.Scan(&name)
				if e == nil {
					_, e = migrationFS.ReadFile("migrations/" + name)
					if e != nil {
						e = ErrSchemaNewerThanImage
					}
				}
			case "workflow_tasks":
				var project, id string
				var version int64
				var raw []byte
				var fields map[string]string
				e = rows.Scan(&project, &id, &version, &raw)
				if e == nil {
					e = json.Unmarshal(raw, &fields)
				}
				if e == nil {
					cost = logical.Workflow(project, id, version, fields)
				}
			case "archive_index":
				var key, ph, project, identity, payload, terms string
				var lexemes []string
				e = rows.Scan(&key, &ph, &project, &identity, &payload, &terms, &lexemes)
				if e == nil {
					cost = logical.ArchiveIndex(key, ph, project, identity, payload, terms, lexemes)
				}
			case "document_index":
				var key, ph, project, identity string
				var raw []byte
				e = rows.Scan(&key, &ph, &project, &identity, &raw)
				if e == nil {
					cost, e = logical.DocumentIndex(key, ph, project, identity, raw)
				}
			}
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
