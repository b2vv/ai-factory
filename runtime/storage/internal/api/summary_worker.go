package api

import (
	"aifactory.local/storage/internal/archive"
	"aifactory.local/storage/internal/control"
	"aifactory.local/storage/internal/retention"
	"aifactory.local/storage/internal/summary"
	"context"
	"errors"
	"reflect"
	"sync"
	"sync/atomic"
	"time"
)

type summaryScope struct{ project, provider string }
type summaryCursor struct {
	epoch      int64
	generation string
	after      *archive.SessionKey
}
type summarySettings struct {
	config  summary.Config
	extract summary.ExtractOptions
}
type summaryWorkerState struct {
	mu              sync.Mutex
	settings        *summarySettings
	nextScope       int
	cursors         map[summaryScope]summaryCursor
	clock           time.Time
	enabled, failed atomic.Bool
}
type summarySnapshot struct {
	query      archive.SummaryQuery
	activation control.SummaryActivation
	policy     uint64
}

// ConfigureSummaries is an explicit, once-per-server opt-in. It inspects the
// existing schema; it installs nothing and never creates consent or indexes.
func (s *Server) ConfigureSummaries(c summary.Config, o summary.ExtractOptions) error {
	if err := c.Validate(); err != nil {
		return err
	}
	if _, err := summary.ExtractiveVersion(o); err != nil {
		return err
	}
	if s.ing == nil || s.measure == nil {
		return errors.New("summary: source/meter unavailable")
	}
	source, ok := s.ing.Store().(archive.SummarySource)
	if !ok {
		return errors.New("summary: metadata source unavailable")
	}
	ready, err := source.SummarySchemaReady()
	if err != nil {
		return err
	}
	if !ready {
		return errors.New("summary: existing metadata schema required")
	}
	w := &s.summaryWorker
	w.mu.Lock()
	defer w.mu.Unlock()
	if w.settings != nil {
		return errors.New("summary: already configured")
	}
	w.settings = &summarySettings{c, o}
	w.cursors = map[summaryScope]summaryCursor{}
	w.enabled.Store(true)
	return nil
}

func sameSummaryActivation(a, b control.SummaryActivation) bool {
	return a.Project == b.Project && a.Provider == b.Provider && a.Generation == b.Generation && a.Ordinal == b.Ordinal && a.ConsentEpoch == b.ConsentEpoch && a.At.Equal(b.At)
}

// Caller holds the existing authority fence. Barriers are checked before any
// original content read, and again on all actual sources immediately at publish.
func (s *Server) summarySnapshotInFence(tx *control.ArchiveTransaction, a control.SummaryActivation, key *archive.SessionKey) (summarySnapshot, bool, error) {
	var out summarySnapshot
	if tx == nil {
		return out, false, errors.New("summary: metadata authority unavailable")
	}
	state, err := tx.State()
	if err != nil {
		return out, false, err
	}
	current, found, err := tx.SummaryActivation(a.Provider)
	if err != nil {
		return out, false, err
	}
	purpose := s.ctl.Registry().ConsentEpoch(a.Project, a.Provider, "summary")
	capture := s.ctl.Registry().ConsentEpoch(a.Project, a.Provider, "capture")
	if !found || !sameSummaryActivation(a, current) || !purpose.Enabled || purpose.Epoch != a.ConsentEpoch || a.ConsentEpoch <= purpose.RevokedThrough || !capture.Enabled || capture.Epoch <= capture.RevokedThrough {
		return out, false, nil
	}
	if !state.MigrationComplete || state.Generation != a.Generation || state.Pending != nil {
		return out, false, errors.New("summary: source commitment unavailable")
	}
	for _, barrier := range s.ctl.Retention().Barriers() {
		if barrier.Project == a.Project && (barrier.Scope == retention.ScopeProject || key != nil && barrier.Scope == retention.ScopeSession && barrier.SessionID == key.SessionID) {
			return out, false, nil
		}
	}
	out = summarySnapshot{query: archive.SummaryQuery{Project: a.Project, Provider: a.Provider, Generation: a.Generation, ActivationOrdinal: a.Ordinal, Through: state.CommittedOrdinal, RevokedThrough: capture.RevokedThrough, CaptureEpoch: capture.Epoch}, activation: a, policy: state.PolicyRevision}
	return out, true, nil
}
func (s *Server) summarySnapshot(a control.SummaryActivation, key *archive.SessionKey) (summarySnapshot, bool, error) {
	s.mutate.Lock()
	defer s.mutate.Unlock()
	var snapshot summarySnapshot
	var eligible bool
	err := s.ctl.WithArchiveWriter(s.operatorPrincipal(), a.Project, func(tx *control.ArchiveTransaction) error {
		var err error
		snapshot, eligible, err = s.summarySnapshotInFence(tx, a, key)
		return err
	})
	return snapshot, eligible, err
}

// SummaryOnce examines one scope/session outside capture requests. Count reports
// newly completed generations, not any prior WAL work reconciled by recovery.
// Due thresholds are eligibility times; bounded polling/backlog adds latency.
func (s *Server) SummaryOnce(ctx context.Context, now time.Time) (count int, err error) {
	w := &s.summaryWorker
	w.mu.Lock()
	defer w.mu.Unlock()
	defer func() { w.failed.Store(err != nil) }()
	if w.settings == nil {
		return 0, nil
	}
	if ctx == nil {
		return 0, errors.New("summary: context required")
	}
	if err = ctx.Err(); err != nil {
		return 0, err
	}
	now = now.UTC()
	if now.IsZero() {
		return 0, errors.New("summary: invalid clock")
	}
	if _, e := now.MarshalJSON(); e != nil {
		return 0, errors.New("summary: invalid clock")
	}
	if !w.clock.IsZero() && now.Before(w.clock) {
		return 0, errors.New("summary: clock regressed; wait for recovery")
	}
	w.clock = now
	if err = s.recoverArchiveContext(ctx); err != nil {
		return 0, err
	}
	if err = s.recoverIndexContext(ctx); err != nil {
		return 0, err
	}
	if err = ctx.Err(); err != nil {
		return 0, err
	}
	source, ok := s.ing.Store().(archive.SummarySource)
	if !ok {
		return 0, errors.New("summary: metadata source unavailable")
	}
	activations, err := s.ctl.SummaryActivations()
	if err != nil {
		return 0, err
	}
	if len(activations) == 0 {
		return 0, nil
	}
	a := activations[w.nextScope%len(activations)]
	w.nextScope = (w.nextScope + 1) % len(activations)
	snapshot, eligible, err := s.summarySnapshot(a, nil)
	if err != nil || !eligible {
		return 0, err
	}
	scope := summaryScope{a.Project, a.Provider}
	cursor := w.cursors[scope]
	if cursor.epoch != a.ConsentEpoch || cursor.generation != a.Generation {
		cursor = summaryCursor{epoch: a.ConsentEpoch, generation: a.Generation}
	}
	key, found, err := nextSummarySessionContext(ctx, source, snapshot.query, cursor.after)
	if err != nil {
		return 0, err
	}
	if !found {
		cursor.after = nil
		w.cursors[scope] = cursor
		return 0, nil
	}
	cursor.after = &key
	w.cursors[scope] = cursor
	checked, eligible, err := s.summarySnapshot(a, &key)
	if err != nil || !eligible {
		return 0, err
	}
	if checked.policy != snapshot.policy {
		return 0, errors.New("summary: authority changed; retry")
	}
	authority := summary.Authority{ConsentEpoch: a.ConsentEpoch, Activation: summary.Baseline{Project: a.Project, Generation: a.Generation, Ordinal: a.Ordinal, At: a.At}}
	// Arrival after the caller's tick but before the snapshot is ordinary capture,
	// not future evidence. Advance the host observation, never move it backwards.
	if current := time.Now().UTC(); current.After(now) {
		now = current
		w.clock = now
	}
	prepared, err := summary.PrepareSessionContext(ctx, source, checked.query, key, authority, now, w.settings.config, w.settings.extract)
	if err != nil || !prepared.Decision.Ready {
		return 0, err
	}
	record, err := summary.SealExtract(prepared.Document, authority, prepared.Decision.Selected, now)
	if err != nil {
		return 0, err
	}
	finalCtx, cancel := context.WithTimeout(ctx, summary.ProofReadBudget)
	defer cancel()
	s.mutate.Lock()
	defer s.mutate.Unlock()
	if err = finalCtx.Err(); err != nil {
		return 0, err
	}
	err = s.ctl.WithArchiveTransaction(s.operatorPrincipal(), a.Project, func(tx *control.ArchiveTransaction) error {
		if e := s.ing.RecoverEnvelopeWithGate(tx, s.publishEnvelopeGateContext(finalCtx, tx)); e != nil {
			return e
		}
		current, eligible, e := s.summarySnapshotInFence(tx, a, &key)
		if e != nil {
			return e
		}
		if !eligible || current.policy != checked.policy {
			return errors.New("summary: authority changed before publish")
		}
		if e := finalCtx.Err(); e != nil {
			return e
		}
		head, found, e := source.SummaryHead(current.query, key)
		if e != nil {
			return e
		}
		if found != (prepared.Head != nil) || found && !reflect.DeepEqual(head, *prepared.Head) {
			return errors.New("summary: head changed; re-observe")
		}
		if e := finalCtx.Err(); e != nil {
			return e
		}
		if found {
			if _, _, e := summary.LoadStoredContext(finalCtx, head, source, time.Now().UTC()); e != nil {
				return e
			}
		}
		originals := make([]archive.Envelope, 0, len(prepared.Decision.Selected))
		records := []archive.Record{record}
		for _, expected := range prepared.Decision.Selected {
			if e := finalCtx.Err(); e != nil {
				return e
			}
			actual, found, e := source.LookupEnvelope(expected.Record)
			if e != nil {
				return e
			}
			if e := finalCtx.Err(); e != nil {
				return e
			}
			if !found || !reflect.DeepEqual(actual, expected) {
				return errors.New("summary: original changed before publish")
			}
			originals = append(originals, actual)
			records = append(records, actual.Record)
		}
		allowed, e := tx.SummaryPolicyAllows(a, records)
		if e != nil {
			return e
		}
		if !allowed {
			return errors.New("summary: current policy denies publish")
		}
		// Recovery, not regeneration, owns an already accepted body. A terminal receipt
		// without its source must never be republished under a fresh ordinal.
		if s.ing.KnownAcceptedIdentity(record) {
			return errors.New("summary: prior durable job requires recovery; no regeneration")
		}

		if _, exists, e := source.LookupEnvelope(record); e != nil {
			return e
		} else if exists {
			return archive.ErrIDConflict
		}
		if e := finalCtx.Err(); e != nil {
			return e
		}
		state, e := tx.State()
		if e != nil {
			return e
		}
		previewTime := time.Now().UTC()
		preview := archive.Envelope{Version: 2, Record: record, Metadata: archive.Metadata{Generation: state.Generation, Ordinal: state.NextOrdinal, CapturedAt: &previewTime, DerivedKind: archive.DerivedSessionExtract}}
		if _, e := summary.VerifyStored(preview, originals, previewTime); e != nil {
			return e
		}
		if e := finalCtx.Err(); e != nil {
			return e
		}
		envelope, e := tx.ReserveSummary(record, a.ConsentEpoch)
		if e != nil {
			return e
		}
		if e := finalCtx.Err(); e != nil {
			return e
		}
		if _, e = summary.VerifyStored(envelope, originals, time.Now().UTC()); e != nil {
			return e
		}
		_, e = s.ing.CommitEnvelope(tx, envelope)
		if e != nil {
			return e
		}
		count = 1
		return nil
	})
	return count, err
}

// Bridge cancellation at the safe boundaries of the legacy context-free read.
// One in-flight backend call retains its own timeout; it is not interrupted here.
func nextSummarySessionContext(ctx context.Context, source archive.SummarySource, q archive.SummaryQuery, after *archive.SessionKey) (archive.SessionKey, bool, error) {
	if err := ctx.Err(); err != nil {
		return archive.SessionKey{}, false, err
	}
	key, found, err := source.NextSummarySession(q, after)
	if err != nil {
		return archive.SessionKey{}, false, err
	}
	if err := ctx.Err(); err != nil {
		return archive.SessionKey{}, false, err
	}
	return key, found, nil
}
