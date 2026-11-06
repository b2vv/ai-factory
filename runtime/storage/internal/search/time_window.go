package search

import (
	"context"
	"encoding/hex"
	"github.com/jackc/pgx/v5"
	"time"
)

type TimePosition struct{ Time, Key string }
type TimedReference struct {
	Before *TimePosition
	Reference
	MetadataHash string
	Ordinal      int64
	Time         string
}
type TimeWindowResult struct {
	References []TimedReference
	Next       *TimePosition
}

func validTimePosition(p *TimePosition) bool {
	if p == nil {
		return true
	}
	key, err := hex.DecodeString(p.Key)
	if err != nil || len(key) != 32 {
		return false
	}
	stamp, err := time.Parse(timeKeyLayout, p.Time)
	return err == nil && stamp.Format(timeKeyLayout) == p.Time
}

// TimeWindow preserves a committed source upper bound across late writes. It
// bounds raw candidates before token matching; an empty page may have Next.
// Current authorization and exact source metadata must still be checked by callers.
func (s *Store) TimeWindow(expected Checkpoint, field string, since *time.Time, after *TimePosition, upper int64, query string) (TimeWindowResult, error) {
	column := ""
	switch field {
	case "source_event_time":
		column = "source_time_key"
	case "captured_at":
		column = "captured_key"
	default:
		return TimeWindowResult{}, ErrCheckpoint
	}
	if s.schemaVersion != 2 || !validCheckpoint(expected) || upper < 0 || upper > expected.Ordinal || len(query) > 4096 || !validTimePosition(after) {
		return TimeWindowResult{}, ErrCheckpoint
	}
	var sinceKey *string
	if since != nil {
		key := since.UTC().Format(timeKeyLayout)
		if len(key) != 30 {
			return TimeWindowResult{}, ErrCheckpoint
		}
		sinceKey = &key
	}
	afterTime, afterKey := "", ""
	if after != nil {
		afterTime = after.Time
		afterKey = after.Key
	}
	ctx, cancel := context.WithTimeout(context.Background(), s.timeout)
	defer cancel()
	tx, err := s.pool.BeginTx(ctx, pgx.TxOptions{IsoLevel: pgx.RepeatableRead, AccessMode: pgx.ReadOnly})
	if err != nil {
		return TimeWindowResult{}, err
	}
	defer tx.Rollback(ctx)
	current, found, err := scanCheckpoint(tx.QueryRow(ctx, `SELECT `+checkpointColumns+` FROM archive_checkpoint WHERE project_hash=$1 AND project=$2`, hash(expected.Project), expected.Project))
	if err != nil {
		return TimeWindowResult{}, err
	}
	if !found || !sameBinding(current, expected) || current.Ordinal < upper {
		return TimeWindowResult{}, ErrCheckpoint
	}
	sql := `SELECT key_hash,identity,payload_hash,metadata_hash,source_ordinal,time_key,CASE WHEN $8='' THEN true ELSE terms @@ plainto_tsquery('simple',$8) END FROM (
 SELECT key_hash,identity,payload_hash,metadata_hash,source_ordinal,` + column + ` AS time_key,terms FROM archive_index
 WHERE project_hash=$1 AND project=$2 AND source_generation=$3 AND source_ordinal<=$4 AND ` + column + ` IS NOT NULL
 AND ($5::text IS NULL OR ` + column + ` >= $5) AND ($6='' OR ` + column + ` < $6 OR (` + column + `=$6 AND key_hash>$7))
 ORDER BY ` + column + ` DESC,key_hash ASC LIMIT 101) bounded ORDER BY time_key DESC,key_hash ASC`
	rows, err := tx.Query(ctx, sql, hash(expected.Project), expected.Project, expected.SourceGeneration, upper, sinceKey, afterTime, afterKey, normalized(query))
	if err != nil {
		return TimeWindowResult{}, err
	}
	out := TimeWindowResult{References: []TimedReference{}}
	var last TimePosition
	count := 0
	for rows.Next() {
		var ref TimedReference
		var key string
		var matches bool
		if err := rows.Scan(&key, &ref.Identity, &ref.PayloadHash, &ref.MetadataHash, &ref.Ordinal, &ref.Time, &matches); err != nil {
			rows.Close()
			return TimeWindowResult{}, err
		}
		if count == MaxWindow {
			copy := last
			out.Next = &copy
			break
		}
		if count > 0 {
			previous := last
			ref.Before = &previous
		} else if after != nil {
			previous := *after
			ref.Before = &previous
		}
		last = TimePosition{Time: ref.Time, Key: key}
		count++
		if matches {
			out.References = append(out.References, ref)
		}
	}
	err = rows.Err()
	rows.Close()
	if err != nil {
		return TimeWindowResult{}, err
	}
	if err := tx.Commit(ctx); err != nil {
		return TimeWindowResult{}, err
	}
	return out, nil
}

func TimestampKey(t time.Time) string { return t.UTC().Format(timeKeyLayout) }
