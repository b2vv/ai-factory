package search

import (
	"aifactory.local/storage/internal/archive"
	"aifactory.local/storage/internal/logical"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"github.com/jackc/pgx/v5"
	"strconv"
	"time"
	"unicode/utf8"
)

// SourceGeneration names authoritative ordering; ProjectionGeneration changes
// on rebuild and independently fences checkpoints/cursors. Neither proves capture completeness.
type Checkpoint = archive.IndexCheckpoint

const timeKeyLayout = "2006-01-02T15:04:05.000000000Z"

var ErrCheckpoint = errors.New("search: metadata checkpoint changed or unavailable")

func validCheckpoint(c Checkpoint) bool {
	if c.Project == "" || c.Ordinal < 0 {
		return false
	}
	for _, s := range []string{c.SourceGeneration, c.ProjectionGeneration} {
		if s == "" || len(s) > 128 || !utf8.ValidString(s) {
			return false
		}
	}
	_, err := strconv.ParseUint(c.PolicyRevision, 10, 64)
	return err == nil
}
func sameBinding(a, b Checkpoint) bool {
	return a.Project == b.Project && a.SourceGeneration == b.SourceGeneration && a.ProjectionGeneration == b.ProjectionGeneration && a.PolicyRevision == b.PolicyRevision
}
func scanCheckpoint(row pgx.Row) (Checkpoint, bool, error) {
	var c Checkpoint
	err := row.Scan(&c.Project, &c.SourceGeneration, &c.ProjectionGeneration, &c.PolicyRevision, &c.Ordinal, &c.Complete)
	if errors.Is(err, pgx.ErrNoRows) {
		return c, false, nil
	}
	if err != nil {
		return c, false, err
	}
	if !validCheckpoint(c) {
		return c, false, ErrCheckpoint
	}
	return c, true, nil
}

const checkpointColumns = "project,source_generation,projection_generation,policy_revision,ordinal,complete"

func (s *Store) Checkpoint(project string) (Checkpoint, bool, error) {
	if s.schemaVersion != 2 {
		return Checkpoint{}, false, ErrCheckpoint
	}
	ctx, cancel := context.WithTimeout(context.Background(), s.timeout)
	defer cancel()
	return scanCheckpoint(s.pool.QueryRow(ctx, `SELECT `+checkpointColumns+` FROM archive_checkpoint WHERE project_hash=$1 AND project=$2`, hash(project), project))
}

// BeginRebuild is idempotent for the exact new generation. Replacing an existing
// projection requires its expected previous generation, preventing a stale reset.
func (s *Store) BeginRebuild(c Checkpoint, previous string) error {
	if s.schemaVersion != 2 || !validCheckpoint(c) || c.Ordinal != 0 || c.Complete {
		return ErrCheckpoint
	}
	ctx, cancel := context.WithTimeout(context.Background(), s.timeout)
	defer cancel()
	tx, err := s.pool.Begin(ctx)
	if err != nil {
		return err
	}
	defer tx.Rollback(ctx)
	inserted, err := tx.Exec(ctx, `INSERT INTO archive_checkpoint(project_hash,project,source_generation,projection_generation,policy_revision,ordinal,complete) VALUES($1,$2,$3,$4,$5,0,false) ON CONFLICT(project_hash) DO NOTHING`, hash(c.Project), c.Project, c.SourceGeneration, c.ProjectionGeneration, c.PolicyRevision)
	if err != nil {
		return err
	}
	current, found, err := scanCheckpoint(tx.QueryRow(ctx, `SELECT `+checkpointColumns+` FROM archive_checkpoint WHERE project_hash=$1 FOR UPDATE`, hash(c.Project)))
	if err != nil {
		return err
	}
	if !found || current.Project != c.Project {
		return ErrCheckpoint
	}
	var prior *Checkpoint
	if inserted.RowsAffected() == 0 {
		prior = &current
	}
	action, err := RebuildDecision(prior, c, previous)
	if err != nil {
		return err
	}
	if action == CheckpointReplay {
		return tx.Commit(ctx)
	}
	if _, err := tx.Exec(ctx, `DELETE FROM archive_index WHERE project_hash=$1 AND project=$2`, hash(c.Project), c.Project); err != nil {
		return err
	}
	if _, err := tx.Exec(ctx, `UPDATE archive_checkpoint SET source_generation=$2,projection_generation=$3,policy_revision=$4,ordinal=0,complete=false WHERE project_hash=$1`, hash(c.Project), c.SourceGeneration, c.ProjectionGeneration, c.PolicyRevision); err != nil {
		return err
	}
	return tx.Commit(ctx)
}
func canonicalMetadata(e archive.Envelope) (archive.Envelope, string, *string, *string, error) {
	raw, err := archive.EncodeEnvelope(e)
	if err != nil {
		return archive.Envelope{}, "", nil, nil, err
	}
	e, err = archive.DecodeEnvelope(2, raw)
	if err != nil {
		return archive.Envelope{}, "", nil, nil, err
	}
	meta, _ := json.Marshal(e.Metadata)
	key := func(t *time.Time) *string {
		if t == nil {
			return nil
		}
		v := t.UTC().Format(timeKeyLayout)
		return &v
	}
	return e, hash(string(meta)), key(e.Metadata.CapturedAt), key(e.Metadata.SourceEventTime), nil
}
func MetadataHash(e archive.Envelope) (string, error) {
	_, h, _, _, err := canonicalMetadata(e)
	return h, err
}
func (s *Store) PutEnvelope(e archive.Envelope, c Checkpoint) error {
	if s.schemaVersion != 2 || !validCheckpoint(c) || len(e.Record.Text) > MaxTextBytes {
		return ErrCheckpoint
	}
	e, mh, captured, event, err := canonicalMetadata(e)
	if err != nil {
		return err
	}
	if e.Record.Project != c.Project || e.Metadata.Generation != c.SourceGeneration || e.Metadata.Ordinal <= c.Ordinal {
		return ErrCheckpoint
	}
	ctx, cancel := context.WithTimeout(context.Background(), s.timeout)
	defer cancel()
	tx, err := s.pool.Begin(ctx)
	if err != nil {
		return err
	}
	defer tx.Rollback(ctx)
	current, found, err := scanCheckpoint(tx.QueryRow(ctx, `SELECT `+checkpointColumns+` FROM archive_checkpoint WHERE project_hash=$1 AND project=$2 FOR UPDATE`, hash(c.Project), c.Project))
	if err != nil {
		return err
	}
	if !found || !sameBinding(current, c) {
		return ErrCheckpoint
	}
	action, err := ProjectionDecision(current, c, e)
	if err != nil {
		return err
	}
	identity := archive.IdentityKey(e.Record)
	if action == CheckpointVerifyRetry {
		var exact bool
		err := tx.QueryRow(ctx, `SELECT EXISTS(SELECT 1 FROM archive_index WHERE key_hash=$1 AND project=$2 AND identity=$3 AND payload_hash=$4 AND metadata_hash=$5 AND source_generation=$6 AND source_ordinal=$7 AND project_hash=$8 AND captured_key IS NOT DISTINCT FROM $9 AND source_time_key IS NOT DISTINCT FROM $10 AND terms=to_tsvector('simple',$11))`, hash(identity), c.Project, identity, RecordHash(e.Record), mh, c.SourceGeneration, e.Metadata.Ordinal, hash(c.Project), captured, event, normalized(e.Record.Text)).Scan(&exact)
		if err != nil {
			return err
		}
		if !exact {
			return ErrCheckpoint
		}
		return tx.Commit(ctx)
	}

	result, err := tx.Exec(ctx, `INSERT INTO archive_index(key_hash,project_hash,project,identity,payload_hash,terms,metadata_hash,source_generation,source_ordinal,captured_key,source_time_key) VALUES($1,$2,$3,$4,$5,to_tsvector('simple',$6),$7,$8,$9,$10,$11)
 ON CONFLICT(key_hash) DO UPDATE SET payload_hash=excluded.payload_hash,terms=excluded.terms,metadata_hash=excluded.metadata_hash,source_generation=excluded.source_generation,source_ordinal=excluded.source_ordinal,captured_key=excluded.captured_key,source_time_key=excluded.source_time_key WHERE archive_index.identity=excluded.identity AND archive_index.project=excluded.project`, hash(identity), hash(c.Project), c.Project, identity, RecordHash(e.Record), normalized(e.Record.Text), mh, c.SourceGeneration, e.Metadata.Ordinal, captured, event)
	if err != nil {
		return err
	}
	if result.RowsAffected() != 1 {
		return fmt.Errorf("search: identity hash collision refused")
	}
	if _, err := tx.Exec(ctx, `UPDATE archive_checkpoint SET ordinal=$2,complete=false WHERE project_hash=$1`, hash(c.Project), e.Metadata.Ordinal); err != nil {
		return err
	}
	return tx.Commit(ctx)
}

// CompleteCheckpoint requires the caller's bounded source scan to prove exhaustion
// through the committed upper bound under the stable control/policy fence.
func (s *Store) CompleteCheckpoint(c Checkpoint, through int64) error {
	if s.schemaVersion != 2 || !validCheckpoint(c) || through < c.Ordinal {
		return ErrCheckpoint
	}
	ctx, cancel := context.WithTimeout(context.Background(), s.timeout)
	defer cancel()
	tx, err := s.pool.Begin(ctx)
	if err != nil {
		return err
	}
	defer tx.Rollback(ctx)
	current, found, err := scanCheckpoint(tx.QueryRow(ctx, `SELECT `+checkpointColumns+` FROM archive_checkpoint WHERE project_hash=$1 AND project=$2 FOR UPDATE`, hash(c.Project), c.Project))
	if err != nil {
		return err
	}
	if !found || !sameBinding(current, c) {
		return ErrCheckpoint
	}
	action, err := CompletionDecision(current, c, through)
	if err != nil {
		return err
	}
	if action == CheckpointReplay {
		return tx.Commit(ctx)
	}
	if _, err := tx.Exec(ctx, `UPDATE archive_checkpoint SET ordinal=$2,complete=true WHERE project_hash=$1`, hash(c.Project), through); err != nil {
		return err
	}
	return tx.Commit(ctx)
}

func (s *Store) ProjectionReservationBytes(e archive.Envelope, c Checkpoint) (int64, error) {
	if s.schemaVersion != 2 || !validCheckpoint(c) || e.Record.Project != c.Project || e.Metadata.Generation != c.SourceGeneration || e.Metadata.Ordinal <= c.Ordinal {
		return 0, ErrCheckpoint
	}
	e, mh, captured, event, err := canonicalMetadata(e)
	if err != nil {
		return 0, err
	}
	base, err := s.ReservationBytes(e.Record)
	if err != nil {
		return 0, err
	}
	identity := archive.IdentityKey(e.Record)
	cost := base + logical.ArchiveMetadata(hash(identity), hash(c.Project), c.Project, c.SourceGeneration, mh, e.Metadata.Ordinal, captured, event)
	// Reserve the whole replacement checkpoint, not merely an assumed byte delta.
	cost += logical.ArchiveCheckpoint(hash(c.Project), c.Project, c.SourceGeneration, c.ProjectionGeneration, c.PolicyRevision, e.Metadata.Ordinal, false)
	return cost, nil
}

func (s *Store) AdvanceCheckpoint(c Checkpoint, through int64) error {
	if s.schemaVersion != 2 || !validCheckpoint(c) || through <= c.Ordinal {
		return ErrCheckpoint
	}
	ctx, cancel := context.WithTimeout(context.Background(), s.timeout)
	defer cancel()
	tx, err := s.pool.Begin(ctx)
	if err != nil {
		return err
	}
	defer tx.Rollback(ctx)
	current, found, err := scanCheckpoint(tx.QueryRow(ctx, `SELECT `+checkpointColumns+` FROM archive_checkpoint WHERE project_hash=$1 AND project=$2 FOR UPDATE`, hash(c.Project), c.Project))
	if err != nil {
		return err
	}
	if !found {
		return ErrCheckpoint
	}
	action, err := ProgressDecision(current, c, through)
	if err != nil {
		return err
	}
	if action == CheckpointReplay {
		return tx.Commit(ctx)
	}
	if _, err := tx.Exec(ctx, `UPDATE archive_checkpoint SET ordinal=$2,complete=false WHERE project_hash=$1`, hash(c.Project), through); err != nil {
		return err
	}
	return tx.Commit(ctx)
}
func (s *Store) CheckpointReservationBytes(c Checkpoint) (int64, error) {
	if s.schemaVersion != 2 || !validCheckpoint(c) {
		return 0, ErrCheckpoint
	}
	return logical.ArchiveCheckpoint(hash(c.Project), c.Project, c.SourceGeneration, c.ProjectionGeneration, c.PolicyRevision, c.Ordinal, c.Complete), nil
}

// MatchesEnvelope verifies every authoritative hash and the exact checkpoint.
// The coordinator holds the source/policy fence and admits no subsequent index
// action before this proof releases the pending intent.
func (s *Store) MatchesEnvelope(e archive.Envelope, c Checkpoint) (bool, error) {
	if s.schemaVersion != 2 {
		return false, ErrCheckpoint
	}
	_, mh, captured, event, err := canonicalMetadata(e)
	if err != nil {
		return false, err
	}
	current, found, err := s.Checkpoint(c.Project)
	if err != nil || !found {
		return false, err
	}
	if current != c {
		return false, nil
	}
	ctx, cancel := context.WithTimeout(context.Background(), s.timeout)
	defer cancel()
	var matches bool
	identity := archive.IdentityKey(e.Record)
	err = s.pool.QueryRow(ctx, `SELECT EXISTS(SELECT 1 FROM archive_index WHERE key_hash=$1 AND project_hash=$2 AND project=$3 AND identity=$4 AND payload_hash=$5 AND metadata_hash=$6 AND source_generation=$7 AND source_ordinal=$8 AND captured_key IS NOT DISTINCT FROM $9 AND source_time_key IS NOT DISTINCT FROM $10 AND terms=to_tsvector('simple',$11))`, hash(identity), hash(c.Project), c.Project, identity, RecordHash(e.Record), mh, e.Metadata.Generation, e.Metadata.Ordinal, captured, event, normalized(e.Record.Text)).Scan(&matches)
	return matches, err
}

func (s *Store) MatchesEmptyRebuild(c Checkpoint) (bool, error) {
	if c.Ordinal != 0 || c.Complete {
		return false, ErrCheckpoint
	}
	current, found, err := s.Checkpoint(c.Project)
	if err != nil || !found {
		return false, err
	}
	if current != c {
		return false, nil
	}
	ctx, cancel := context.WithTimeout(context.Background(), s.timeout)
	defer cancel()
	var empty bool
	err = s.pool.QueryRow(ctx, `SELECT NOT EXISTS(SELECT 1 FROM archive_index WHERE project=$1)`, c.Project).Scan(&empty)
	return empty, err
}
