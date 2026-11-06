package api

import (
	"aifactory.local/storage/internal/archive"
	"aifactory.local/storage/internal/capture"
	"aifactory.local/storage/internal/control"
	"aifactory.local/storage/internal/wal"
	"errors"
	"net/http"
	"time"
)

var errMetadataPolicy = errors.New("capture record denied by current retention policy")

func (s *Server) withArchiveWriter(w http.ResponseWriter, project string, action func(http.ResponseWriter, *control.ArchiveTransaction)) {
	s.withMutation(w, func(buffer http.ResponseWriter) {
		err := s.ctl.WithArchiveWriter(s.operatorPrincipal(), project, func(tx *control.ArchiveTransaction) error { action(buffer, tx); return nil })
		if err != nil {
			writeErr(buffer, 503, "control archive authority unavailable; retry after recovery")
		}
	})
}
func (s *Server) captureMetadata(w http.ResponseWriter, tx *control.ArchiveTransaction, records []archive.Record, red []capture.Redaction, attempts []string, sourceTimes []*time.Time) bool {
	accepted := 0
	receipts := []string{}
	fail := func(err error) bool {
		code := 503
		if errors.Is(err, archive.ErrIDConflict) || errors.Is(err, wal.ErrKeyConflict) || errors.Is(err, errMetadataPolicy) {
			code = 409
		}
		writeJSON(w, code, map[string]any{"accepted": accepted, "receipts": receipts, "attempt_receipts": attempts, "outcome": "inspect_receipts", "error": err.Error()})
		return false
	}
	if err := s.ing.RecoverEnvelope(tx, s.publishGate); err != nil {
		return fail(err)
	}
	state, err := tx.State()
	if err != nil {
		return fail(err)
	}
	if !state.MigrationComplete {
		return fail(errors.New("archive metadata migration incomplete"))
	}
	source, ok := s.ing.Store().(archive.MetadataStore)
	if !ok {
		return fail(errors.New("archive metadata storage unavailable"))
	}
	for n, r := range records {
		var eventTime *time.Time
		if len(sourceTimes) > 0 {
			eventTime = sourceTimes[n]
		}
		if !s.publishGate(r) {
			return fail(errMetadataPolicy)
		}
		state, err = tx.State()
		if err != nil {
			return fail(err)
		}
		prior, found, err := source.LookupEnvelope(r)
		if err != nil {
			return fail(err)
		}
		key := archive.IdentityKey(r)
		if found && state.Pending == nil {
			if eventTime != nil && prior.Metadata.SourceEventTime != nil && !eventTime.Equal(*prior.Metadata.SourceEventTime) {
				return fail(archive.ErrIDConflict)
			}
			if prior.Record != r {
				return fail(archive.ErrIDConflict)
			}
			if prior.Version != 2 || prior.Metadata.Generation != state.Generation || prior.Metadata.Ordinal > state.CommittedOrdinal {
				return fail(errors.New("archive source commitment mismatch"))
			}
			accepted++
			receipts = append(receipts, key)
			continue
		}
		e, err := tx.Reserve(r, eventTime, false)
		if err != nil {
			return fail(err)
		}
		receipt, err := s.ing.CommitEnvelope(tx, e)
		if receipt.Seq > 0 {
			receipts = append(receipts, key)
		}
		if err != nil {
			return fail(err)
		}
		accepted++
	}
	writeJSON(w, 200, map[string]any{"accepted": accepted, "committed": accepted, "receipts": receipts, "redactions": red})
	return true
}

// RecoverArchive runs before startup markers, workers and LISTEN. It also runs
// before ordinary drains so transient source outages need no producer retry.
func (s *Server) RecoverArchive() error {
	s.mutate.Lock()
	defer s.mutate.Unlock()
	return s.recoverArchiveLocked()
}
func (s *Server) recoverArchiveLocked() error {
	for _, project := range s.ctl.Registry().Projects() {
		if err := s.ctl.WithArchiveWriter(s.operatorPrincipal(), project, func(tx *control.ArchiveTransaction) error {
			if tx == nil {
				return nil
			}
			state, err := tx.State()
			if err != nil {
				return err
			}
			if !state.MigrationComplete {
				return errors.New("archive metadata migration incomplete; resume offline migration")
			}
			if s.ing == nil {
				return errors.New("activated archive requires existing intake and source")
			}
			return s.ing.RecoverEnvelope(tx, s.publishGate)
		}); err != nil {
			return err
		}
	}
	if ledger := s.ctl.Budget(); ledger != nil {
		pending := ledger.Snapshot().Pending
		if len(pending) == 1 && pending[0].Evidence.Kind == "archive-source-v2" {
			return s.ctl.RecoverUnreservedArchiveIntent(s.operatorPrincipal())
		}
	}
	return nil
}
