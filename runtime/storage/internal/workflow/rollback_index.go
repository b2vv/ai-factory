package workflow

import (
	"context"
	"encoding/json"
	"fmt"
	"github.com/jackc/pgx/v5"
)

// Derived tables require exact shape and exclusive locks. Nonempty indexes
// additionally require a coordinator-supplied verified source/rebuild proof;
// the low-level path refuses when that proof is absent.
type DerivedIndexRecord struct{ Project, Identity, PayloadHash string }
type DerivedDocumentRecord struct {
	Project string
	Data    json.RawMessage
}

func verifyDerivedIndex(ctx context.Context, tx pgx.Tx, verify func([]DerivedIndexRecord, []DerivedDocumentRecord) error) error {
	if _, e := tx.Exec(ctx, `LOCK TABLE archive_index,document_index,derived_index_version IN ACCESS EXCLUSIVE MODE`); e != nil {
		return e
	}
	shapes := map[string][]string{
		"archive_index":         {"key_hash:text", "project_hash:text", "project:text", "identity:text", "payload_hash:text", "terms:tsvector"},
		"document_index":        {"key_hash:text", "project_hash:text", "project:text", "identity:text", "data:jsonb"},
		"derived_index_version": {"singleton:boolean", "version:integer"},
	}
	for table, want := range shapes {
		rows, e := tx.Query(ctx, `SELECT attname||':'||format_type(atttypid,atttypmod),attnotnull FROM pg_attribute WHERE attrelid=$1::regclass AND attnum>0 AND NOT attisdropped ORDER BY attnum`, table)
		if e != nil {
			return e
		}
		n := 0
		for rows.Next() {
			var field string
			var required bool
			if e = rows.Scan(&field, &required); e != nil {
				rows.Close()
				return e
			}
			if n >= len(want) || field != want[n] || !required {
				rows.Close()
				return fmt.Errorf("workflow: derived index shape differs from reviewed migration")
			}
			n++
		}
		rows.Close()
		if e = rows.Err(); e != nil {
			return e
		}
		if n != len(want) {
			return fmt.Errorf("workflow: incomplete derived index shape")
		}
	}
	var valid bool
	if e := tx.QueryRow(ctx, `SELECT count(*)=1 AND bool_and(singleton AND version=1) FROM derived_index_version`).Scan(&valid); e != nil {
		return e
	}
	if !valid {
		return fmt.Errorf("workflow: unknown derived index version")
	}
	if e := tx.QueryRow(ctx, `SELECT NOT EXISTS(SELECT 1 FROM archive_index) AND NOT EXISTS(SELECT 1 FROM document_index)`).Scan(&valid); e != nil {
		return e
	}
	if !valid {
		if verify == nil {
			return fmt.Errorf("workflow: nonempty derived index requires verified source/rebuild recovery before rollback; refusing")
		}
		archives := []DerivedIndexRecord{}
		docs := []DerivedDocumentRecord{}
		used := 0
		rows, e := tx.Query(ctx, `SELECT project,identity,payload_hash FROM archive_index ORDER BY key_hash LIMIT 100001`)
		if e != nil {
			return e
		}
		for rows.Next() {
			var r DerivedIndexRecord
			if e = rows.Scan(&r.Project, &r.Identity, &r.PayloadHash); e != nil {
				rows.Close()
				return e
			}
			used += len(r.Project) + len(r.Identity) + len(r.PayloadHash) + 64
			if used > 32<<20 || len(archives) >= 100000 {
				rows.Close()
				return fmt.Errorf("workflow: index proof bound exceeded")
			}
			archives = append(archives, r)
		}
		rows.Close()
		if e = rows.Err(); e != nil {
			return e
		}
		rows, e = tx.Query(ctx, `SELECT project,data FROM document_index ORDER BY key_hash LIMIT 100001`)
		if e != nil {
			return e
		}
		for rows.Next() {
			var r DerivedDocumentRecord
			if e = rows.Scan(&r.Project, &r.Data); e != nil {
				rows.Close()
				return e
			}
			used += len(r.Project) + len(r.Data) + 64
			if used > 32<<20 || len(docs) >= 100000 {
				rows.Close()
				return fmt.Errorf("workflow: document proof bound exceeded")
			}
			docs = append(docs, r)
		}
		rows.Close()
		if e = rows.Err(); e != nil {
			return e
		}
		if e = verify(archives, docs); e != nil {
			return e
		}
	}

	return nil
}
