// Package search owns only rebuildable PostgreSQL projections. Mongo records and
// explicitly supplied Markdown sources remain authoritative; an index is never
// a fallback source for content, grants, consent or workflow ownership.
package search

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"time"

	"aifactory.local/storage/internal/archive"
	"aifactory.local/storage/internal/budget"
	"aifactory.local/storage/internal/logical"
	"aifactory.local/storage/internal/workflow"
	"github.com/jackc/pgx/v5/pgxpool"
	"golang.org/x/text/cases"
	"golang.org/x/text/unicode/norm"
)

const SchemaVersion = 2
const MaxWindow = 100
const MaxTextBytes = 8 << 20

type Reference struct {
	Key         string `json:"-"`
	Identity    string
	PayloadHash string
}

type Store struct {
	schemaVersion int
	pool          *pgxpool.Pool
	timeout       time.Duration
}

func hash(s string) string               { b := sha256.Sum256([]byte(s)); return hex.EncodeToString(b[:]) }
func RecordHash(r archive.Record) string { b, _ := json.Marshal(r); return hash(string(b)) }
func normalized(s string) string {
	return norm.NFC.String(cases.Fold().String(norm.NFC.String(tokenBoundaries(s))))
}

// The derived index has its own schema/version because workflow ownership and
// workflow rollback must not implicitly own or drop search projections.
func Open(ctx context.Context, dsn string) (*Store, error) {
	// The central migration registry binds older images as well as this component.
	// Workflow ownership remains unchanged: opening PG never transfers authority.
	schema, e := workflow.OpenPostgres(ctx, dsn)
	if e != nil {
		return nil, e
	}
	schema.Close()
	pool, e := pgxpool.New(ctx, dsn)
	if e != nil {
		return nil, e
	}
	var version int
	if e = pool.QueryRow(ctx, `SELECT version FROM derived_index_version WHERE singleton=true`).Scan(&version); e != nil {
		pool.Close()
		return nil, e
	}
	if version != 1 && version != SchemaVersion {
		pool.Close()
		return nil, fmt.Errorf("search: unsupported index schema %d", version)
	}
	return &Store{pool: pool, timeout: 3 * time.Second, schemaVersion: version}, nil
}

func (s *Store) Close() { s.pool.Close() }
func (s *Store) Put(r archive.Record) error {
	if len(r.Text) > MaxTextBytes {
		return fmt.Errorf("search: input exceeds bounded record limit")
	}
	ctx, cancel := context.WithTimeout(context.Background(), s.timeout)
	defer cancel()
	identity := archive.IdentityKey(r)
	result, e := s.pool.Exec(ctx, `INSERT INTO archive_index(key_hash,project_hash,project,identity,payload_hash,terms)
 VALUES($1,$2,$3,$4,$5,to_tsvector('simple',$6))
 ON CONFLICT(key_hash) DO UPDATE SET payload_hash=excluded.payload_hash,terms=excluded.terms
 WHERE archive_index.identity=excluded.identity AND archive_index.project=excluded.project`, hash(identity), hash(r.Project), r.Project, identity, RecordHash(r), normalized(r.Text))
	if e != nil {
		return e
	}
	if result.RowsAffected() != 1 {
		return fmt.Errorf("search: identity hash collision refused")
	}
	return nil
}
func (s *Store) Matches(r archive.Record) (bool, error) {
	ctx, cancel := context.WithTimeout(context.Background(), s.timeout)
	defer cancel()
	var matches bool
	identity := archive.IdentityKey(r)
	e := s.pool.QueryRow(ctx, `SELECT EXISTS(SELECT 1 FROM archive_index WHERE key_hash=$1 AND identity=$2 AND project=$3 AND payload_hash=$4)`, hash(identity), identity, r.Project, RecordHash(r)).Scan(&matches)
	return matches, e
}
func (s *Store) Delete(r archive.Record) error {
	ctx, cancel := context.WithTimeout(context.Background(), s.timeout)
	defer cancel()
	_, e := s.pool.Exec(ctx, `DELETE FROM archive_index WHERE key_hash=$1 AND identity=$2 AND project=$3`, hash(archive.IdentityKey(r)), archive.IdentityKey(r), r.Project)
	return e
}
func (s *Store) Purge(project string) error {
	ctx, cancel := context.WithTimeout(context.Background(), s.timeout)
	defer cancel()
	tx, e := s.pool.Begin(ctx)
	if e != nil {
		return e
	}
	defer tx.Rollback(ctx)
	tables := []string{"archive_index", "document_index"}
	if s.schemaVersion == 2 {
		tables = append(tables, "archive_checkpoint")
	}
	for _, table := range tables {
		if _, e = tx.Exec(ctx, "DELETE FROM "+table+" WHERE project_hash=$1 AND project=$2", hash(project), project); e != nil {
			return e
		}
	}
	return tx.Commit(ctx)
}

// Window bounds DB work by a keyset of at most MaxWindow candidates, applying
// tokenized matching within that window. The caller must verify current source
// hashes and privacy authority before exposing content. Next advances past the
// raw window even if no terms match. No global total or source payload is returned.
func (s *Store) Window(project, query, after string) (refs []Reference, next string, err error) {
	if len(query) > 4096 || (after != "" && len(after) != 64) {
		return nil, "", fmt.Errorf("search: invalid bounded query/cursor")
	}
	ctx, cancel := context.WithTimeout(context.Background(), s.timeout)
	defer cancel()
	rows, e := s.pool.Query(ctx, `SELECT key_hash,identity,payload_hash,CASE WHEN $4='' THEN true ELSE terms @@ plainto_tsquery('simple',$4) END
 FROM (SELECT key_hash,identity,payload_hash,terms FROM archive_index WHERE project_hash=$1 AND project=$2 AND key_hash>$3 ORDER BY key_hash LIMIT 101) bounded
 ORDER BY key_hash`, hash(project), project, after, normalized(query))
	if e != nil {
		return nil, "", e
	}
	defer rows.Close()
	count := 0
	last := ""
	for rows.Next() {
		var key string
		var ref Reference
		var matched bool
		if e = rows.Scan(&key, &ref.Identity, &ref.PayloadHash, &matched); e != nil {
			return nil, "", e
		}
		if key != hash(ref.Identity) {
			return nil, "", ErrCheckpoint
		}
		ref.Key = key
		if count == MaxWindow {
			next = last
			break
		}
		count++
		last = key
		if matched {
			refs = append(refs, ref)
		}
	}
	return refs, next, rows.Err()
}

// ReservationBytes asks the same PostgreSQL dictionary used by Put to produce
// its exact logical term vector and declared index postings before admission.
func (s *Store) ReservationBytes(r archive.Record) (int64, error) {
	if len(r.Text) > MaxTextBytes {
		return 0, fmt.Errorf("search: input exceeds bounded record limit")
	}
	ctx, cancel := context.WithTimeout(context.Background(), s.timeout)
	defer cancel()
	var terms string
	var lexemes []string
	e := s.pool.QueryRow(ctx, `SELECT v::text,tsvector_to_array(v) FROM (SELECT to_tsvector('simple',$1) v) parsed`, normalized(r.Text)).Scan(&terms, &lexemes)
	if e != nil {
		return 0, e
	}
	identity := archive.IdentityKey(r)
	return logical.ArchiveIndex(hash(identity), hash(r.Project), r.Project, identity, RecordHash(r), terms, lexemes), nil
}

func IndexEvidence(r archive.Record) budget.Evidence {
	return budget.Evidence{Kind: "archive-index", KeyHash: hash(archive.IdentityKey(r)), PayloadHash: RecordHash(r)}
}
