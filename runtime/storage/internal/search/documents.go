package search

import (
	"aifactory.local/storage/internal/documents"
	"aifactory.local/storage/internal/logical"
	"context"
	"encoding/json"
	"fmt"
)

type DocumentReference struct {
	Root           string
	Ledger         string
	LedgerRevision string
	documents.Entry
}

// ReplaceDocuments validates the complete explicitly enrolled authoritative ledger
// and its sources. Deleted rows are retained as metadata tombstones. A changed
// ledger after commit is surfaced and cannot pass the serving revision check.
func (s *Store) ReplaceDocuments(project, root, ledger, expected string) error {
	return s.ReplaceDocumentsBudgeted(project, root, ledger, expected, nil)
}

// ReplaceDocumentsBudgeted preflights all replacement rows and declared key
// representations before the first DELETE/INSERT. SQL allocation remains distinct.
func (s *Store) ReplaceDocumentsBudgeted(project, root, ledger, expected string, reserve func(int64) error) error {
	path, e := documents.LedgerPath(root, ledger)
	if e != nil {
		return e
	}
	rows, revision, e := documents.Read(path)
	if e != nil {
		return e
	}
	if revision != expected {
		return fmt.Errorf("search: document ledger revision conflict")
	}
	for _, row := range rows {
		if e = documents.VerifySource(root, row); e != nil {
			return e
		}
	}
	if reserve != nil {
		var cost int64
		for _, row := range rows {
			identity, _ := json.Marshal([]string{project, row.ID})
			raw, e := json.Marshal(DocumentReference{Root: root, Ledger: ledger, LedgerRevision: revision, Entry: row})
			if e != nil {
				return e
			}
			rowCost, e := logical.DocumentIndex(hash(string(identity)), hash(project), project, string(identity), raw)
			if e != nil {
				return e
			}
			cost += rowCost
		}
		if e = reserve(cost); e != nil {
			return e
		}
	}
	ctx, cancel := context.WithTimeout(context.Background(), s.timeout)
	defer cancel()
	tx, e := s.pool.Begin(ctx)
	if e != nil {
		return e
	}
	defer tx.Rollback(ctx)
	if _, e = tx.Exec(ctx, `DELETE FROM document_index WHERE project_hash=$1 AND project=$2`, hash(project), project); e != nil {
		return e
	}
	for _, row := range rows {
		identityBytes, _ := json.Marshal([]string{project, row.ID})
		identity := string(identityBytes)
		raw, e := json.Marshal(DocumentReference{Root: root, Ledger: ledger, LedgerRevision: revision, Entry: row})
		if e != nil {
			return e
		}
		if _, e = tx.Exec(ctx, `INSERT INTO document_index(key_hash,project_hash,project,identity,data) VALUES($1,$2,$3,$4,$5)`, hash(identity), hash(project), project, identity, raw); e != nil {
			return e
		}
	}
	_, check, e := documents.Read(path)
	if e != nil {
		return e
	}
	if check != expected {
		return fmt.Errorf("search: source ledger changed during indexing")
	}
	return tx.Commit(ctx)
}
func (s *Store) DocumentWindow(project, after string) (refs []DocumentReference, next string, err error) {
	ctx, cancel := context.WithTimeout(context.Background(), s.timeout)
	defer cancel()
	rows, e := s.pool.Query(ctx, `SELECT key_hash,data FROM document_index WHERE project_hash=$1 AND project=$2 AND key_hash>$3 ORDER BY key_hash LIMIT 101`, hash(project), project, after)
	if e != nil {
		return nil, "", e
	}
	defer rows.Close()
	count := 0
	last := ""
	for rows.Next() {
		var key string
		var raw []byte
		if e = rows.Scan(&key, &raw); e != nil {
			return nil, "", e
		}
		if count == MaxWindow {
			next = last
			break
		}
		count++
		last = key
		var ref DocumentReference
		if e = json.Unmarshal(raw, &ref); e != nil {
			return nil, "", e
		}
		refs = append(refs, ref)
	}
	return refs, next, rows.Err()
}

// ValidateDocument refuses stale derived references, including ledger tombstones
// added after indexing. No PG row is treated as authoritative document state.
func ValidateDocument(ref DocumentReference) error {
	path, e := documents.LedgerPath(ref.Root, ref.Ledger)
	if e != nil {
		return e
	}
	rows, revision, e := documents.Read(path)
	if e != nil {
		return e
	}
	if revision != ref.LedgerRevision {
		return fmt.Errorf("search: stale document ledger")
	}
	for _, row := range rows {
		if row.ID == ref.ID {
			if row != ref.Entry {
				return fmt.Errorf("search: source metadata mismatch")
			}
			return documents.VerifySource(ref.Root, row)
		}
	}
	return fmt.Errorf("search: document absent from authoritative ledger")
}
