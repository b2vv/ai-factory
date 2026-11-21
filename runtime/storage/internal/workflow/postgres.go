// PGStore is the production structured-workflow backend: a real PostgreSQL-backed
// implementation of the Store interface, used only when a project is explicitly cut over
// to PostgreSQL ownership (D2). Markdown stays authoritative by default; this store holds
// the structured index/working copy for opt-in PG-owned projects.
//
// Concurrency: CAS is optimistic-version fenced in a single statement, so a stale writer
// (wrong expectedVersion) cannot clobber a newer row. This complements the registry's
// authority/cutover epoch fence enforced by the Manager: version fences concurrent task
// writers; the epoch fence stops a pre-cutover writer from landing after a flip.
//
// Availability is a cached flag refreshed by Ping; an enabled-but-down backend reports
// down (never a fabricated healthy) and the Manager fails closed (ErrBlockedPGDown).
package workflow

import (
	"context"
	"embed"
	"encoding/json"
	"errors"
	"fmt"
	"sort"
	"sync/atomic"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
)

//go:embed migrations/*.sql migrations/down/*.sql
var migrationFS embed.FS

// ErrSchemaNewerThanImage is returned when the database carries a migration this binary does
// NOT embed, i.e. the DB schema was advanced by a NEWER image. Per acceptance B5 (schema
// version bound to image version), a binary must refuse to operate on a schema it does not
// understand rather than risk corrupting newer state. This is the fail-closed half of the
// binding. The initial migration has a separately gated operator rollback path;
// unknown later migrations still refuse (see deploy/oci/manifest.json schema_binding).
var ErrSchemaNewerThanImage = errors.New("workflow: database schema is newer than this image knows; refusing to run (fail-closed)")

// ErrVersionConflict is returned by CAS when the stored version does not match the
// expected version (optimistic-concurrency fence), so a stale writer is rejected rather
// than overwriting newer state.
var ErrVersionConflict = errors.New("workflow: version conflict (optimistic CAS fence rejected a stale writer)")

// PGStore implements Store against a real PostgreSQL deployment.
type PGStore struct {
	pool      *pgxpool.Pool
	up        atomic.Bool
	opTimeout time.Duration
}

// OpenPostgres connects, verifies the connection, and applies migrations. It returns an
// error if the backend is unreachable or migrations fail, so an enabled-but-broken backend
// never starts as if healthy.
func OpenPostgres(ctx context.Context, dsn string) (*PGStore, error) {
	return openPostgres(ctx, dsn, true)
}

// OpenPostgresForMaintenance connects without creating or upgrading schema. A
// rollback command must never silently migrate up before evaluating a down step.
func OpenPostgresForMaintenance(ctx context.Context, dsn string) (*PGStore, error) {
	return openPostgres(ctx, dsn, false)
}
func openPostgres(ctx context.Context, dsn string, applyMigrations bool) (*PGStore, error) {
	pool, err := pgxpool.New(ctx, dsn)
	if err != nil {
		return nil, err
	}
	s := &PGStore{pool: pool, opTimeout: 5 * time.Second}
	if err := s.Ping(ctx); err != nil {
		pool.Close()
		return nil, err
	}
	if applyMigrations {
		if err := s.migrate(ctx); err != nil {
			pool.Close()
			return nil, err
		}
	}
	return s, nil
}

// migrate applies embedded SQL migrations in lexical order, each once, tracked in a
// schema_migrations table inside a transaction.
func (s *PGStore) migrate(ctx context.Context) error {
	mctx, cancel := context.WithTimeout(ctx, 30*time.Second)
	defer cancel()
	if _, err := s.pool.Exec(mctx, `CREATE TABLE IF NOT EXISTS schema_migrations (name text PRIMARY KEY, applied_at timestamptz NOT NULL DEFAULT now())`); err != nil {
		return err
	}
	entries, err := migrationFS.ReadDir("migrations")
	if err != nil {
		return err
	}
	names := make([]string, 0, len(entries))
	for _, e := range entries {
		if !e.IsDir() {
			names = append(names, e.Name())
		}
	}
	sort.Strings(names)
	known := make(map[string]bool, len(names))
	for _, n := range names {
		known[n] = true
	}
	// Binding guard (B5): refuse to run if the DB already carries a migration this binary does
	// not embed (a newer image advanced the schema). Checked BEFORE applying, so a downgraded
	// binary never writes against a newer schema it cannot understand.
	rows, err := s.pool.Query(mctx, `SELECT name FROM schema_migrations`)
	if err != nil {
		return err
	}
	for rows.Next() {
		var dbName string
		if err := rows.Scan(&dbName); err != nil {
			rows.Close()
			return err
		}
		if !known[dbName] {
			rows.Close()
			return fmt.Errorf("%w: DB has migration %q not embedded in this image (embedded through %q)", ErrSchemaNewerThanImage, dbName, lastOf(names))
		}
	}
	rows.Close()
	if err := rows.Err(); err != nil {
		return err
	}
	for _, name := range names {
		if name == ArchiveMetadataMigration {
			continue
		} // explicit control-witness upgrade only
		var exists bool
		if err := s.pool.QueryRow(mctx, `SELECT EXISTS(SELECT 1 FROM schema_migrations WHERE name=$1)`, name).Scan(&exists); err != nil {
			return err
		}
		if exists {
			continue
		}
		sqlBytes, err := migrationFS.ReadFile("migrations/" + name)
		if err != nil {
			return err
		}
		tx, err := s.pool.Begin(mctx)
		if err != nil {
			return err
		}
		if _, err = tx.Exec(mctx, `SELECT pg_advisory_xact_lock(170113,0)`); err != nil {
			_ = tx.Rollback(mctx)
			return err
		}
		if err = tx.QueryRow(mctx, `SELECT EXISTS(SELECT 1 FROM schema_migrations WHERE name=$1)`, name).Scan(&exists); err != nil {
			_ = tx.Rollback(mctx)
			return err
		}
		if exists {
			_ = tx.Rollback(mctx)
			continue
		}
		if _, err := tx.Exec(mctx, string(sqlBytes)); err != nil {
			_ = tx.Rollback(mctx)
			return err
		}
		if _, err := tx.Exec(mctx, `INSERT INTO schema_migrations(name) VALUES($1)`, name); err != nil {
			_ = tx.Rollback(mctx)
			return err
		}
		if err := tx.Commit(mctx); err != nil {
			return err
		}
	}
	return nil
}

func lastOf(ss []string) string {
	if len(ss) == 0 {
		return "(none)"
	}
	return ss[len(ss)-1]
}

// SchemaVersion reports the number of migrations embedded in THIS binary (the schema version
// the image understands). It is recorded in the OCI manifest's schema_binding and lets the
// composition root surface the image<->schema binding (B5).
func SchemaVersion() int {
	entries, err := migrationFS.ReadDir("migrations")
	if err != nil {
		return 0
	}
	n := 0
	for _, e := range entries {
		if !e.IsDir() {
			n++
		}
	}
	return n
}

// Ping refreshes and returns the real backend availability.
func (s *PGStore) Ping(ctx context.Context) error {
	pctx, cancel := context.WithTimeout(ctx, s.opTimeout)
	defer cancel()
	err := s.pool.Ping(pctx)
	s.up.Store(err == nil)
	return err
}

// Available reports the last observed backend state (refreshed by Ping).
func (s *PGStore) Available() bool { return s.up.Load() }

// Get returns the stored task and distinguishes absence from a backend or decode error.
func (s *PGStore) Get(project, id string) (Task, bool, error) {
	ctx, cancel := context.WithTimeout(context.Background(), s.opTimeout)
	defer cancel()
	var t Task
	var raw []byte
	err := s.pool.QueryRow(ctx, `SELECT version, fields FROM workflow_tasks WHERE project=$1 AND id=$2`, project, id).Scan(&t.Version, &raw)
	if errors.Is(err, pgx.ErrNoRows) {
		s.up.Store(true)
		return Task{}, false, nil
	}
	if err != nil {
		s.up.Store(false)
		return Task{}, false, err
	}
	if err := json.Unmarshal(raw, &t.Fields); err != nil {
		return Task{}, false, fmt.Errorf("workflow: invalid stored fields: %w", err)
	}
	t.ID = id
	s.up.Store(true)
	return t, true, nil
}

// CAS writes t only if the currently-stored version equals expectedVersion (0 for a
// brand-new task). It is a single optimistic-concurrency statement: a mismatched version
// changes no row and returns ErrVersionConflict, so a stale writer never overwrites newer
// state. Any backend error marks the store unavailable and is returned (never swallowed).
func (s *PGStore) CAS(project string, t Task, expectedVersion int64) error {
	ctx, cancel := context.WithTimeout(context.Background(), s.opTimeout)
	defer cancel()
	fields, err := json.Marshal(t.Fields)
	if err != nil {
		return err
	}
	if expectedVersion < 0 || t.Version != expectedVersion+1 || t.Version <= 0 || t.ID == "" {
		return ErrVersionConflict
	}
	var changed int64
	if expectedVersion == 0 {
		tag, e := s.pool.Exec(ctx, `INSERT INTO workflow_tasks (project,id,version,fields) VALUES ($1,$2,$3,$4) ON CONFLICT (project,id) DO NOTHING`, project, t.ID, t.Version, fields)
		err = e
		changed = tag.RowsAffected()
	} else {
		tag, e := s.pool.Exec(ctx, `UPDATE workflow_tasks SET version=$3, fields=$4 WHERE project=$1 AND id=$2 AND version=$5`, project, t.ID, t.Version, fields, expectedVersion)
		err = e
		changed = tag.RowsAffected()
	}
	if err != nil {
		s.up.Store(false)
		return err
	}
	s.up.Store(true)
	if changed == 0 {
		return ErrVersionConflict
	}
	return nil
}

// StorageBytes returns the PostgreSQL database's on-disk size, so the capacity meter can
// account the PG index/working-copy toward the D4 live-data cap (it was previously omitted).
// An error is returned (never a silent 0) so the caller fails closed.
func (s *PGStore) StorageBytes(ctx context.Context) (int64, error) {
	cctx, cancel := context.WithTimeout(ctx, s.opTimeout)
	defer cancel()
	var n int64
	if err := s.pool.QueryRow(cctx, `SELECT pg_database_size(current_database())`).Scan(&n); err != nil {
		return 0, err
	}
	return n, nil
}

// Close releases the connection pool.
func (s *PGStore) Close() { s.pool.Close() }
