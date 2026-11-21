package api_test

import (
	"aifactory.local/storage/internal/archive"
	"aifactory.local/storage/internal/control"
	"aifactory.local/storage/internal/registry"
	"aifactory.local/storage/internal/summary"
	"context"
	"errors"
	"net/http"
	"net/url"
	"strings"
	"testing"
	"time"
)

func TestSummaryWorkerDefaultsOffThenPublishesOnlyNewOriginals(t *testing.T) {
	f := newSummaryHTTPFixture(t)
	body := map[string]any{"project": "p", "provider": "synthetic", "source_instance": "i", "messages": []map[string]any{{"session_id": "s", "message_id": "next", "role": "user", "text": "New synthetic source for automatic extract"}}}
	if code, _ := do(t, http.MethodPost, f.http.URL+"/v1/capture", opHdr(), body); code != 200 {
		t.Fatal("new source capture", code)
	}
	countSummaries := func() int {
		t.Helper()
		records, err := f.store.Fetch("p")
		if err != nil {
			t.Fatal(err)
		}
		count := 0
		for _, r := range records {
			if r.Type == archive.TypeSummary {
				count++
			}
		}
		return count
	}
	if count, err := f.server.SummaryOnce(context.Background(), time.Now().UTC()); err != nil || count != 0 || countSummaries() != 1 {
		t.Fatal("default-off worker wrote", count, err)
	}
	c := summary.DefaultConfig()
	c.IdleAfter = time.Nanosecond
	if err := f.server.ConfigureSummaries(c, summary.DefaultExtractOptions()); err != nil {
		t.Fatal(err)
	}
	if count, err := f.server.SummaryOnce(context.Background(), time.Now().UTC()); err != nil || count != 1 || countSummaries() != 2 {
		t.Fatal("new original not summarized", count, err)
	}
	for n := 0; n < 2; n++ {
		if count, err := f.server.SummaryOnce(context.Background(), time.Now().UTC()); err != nil || count != 0 {
			t.Fatal("unchanged session repeated", count, err)
		}
	}
	state, _, err := f.control.ArchiveState("p")
	if err != nil {
		t.Fatal(err)
	}
	head, found, err := f.store.SummaryHead(archive.SummaryQuery{Project: "p", Provider: "synthetic", Generation: "g", Through: state.CommittedOrdinal, CaptureEpoch: 1}, archive.SessionKey{SourceInstance: "i", SessionID: "s"})
	if err != nil || !found {
		t.Fatal("newest extract missing", err)
	}
	proof, originals, err := summary.LoadStored(head, f.store, time.Now().UTC())
	if err != nil || len(originals) != 1 || originals[0].Record.MessageID != "next" || proof.Document.Manifest.Progress == nil || proof.Document.Manifest.Progress.AfterOrdinal != 1 || proof.Document.Manifest.CaptureCompleteness != "unknown" {
		t.Fatal("false progress or duplicate history", err)
	}
}

type summaryObservationFault struct {
	*archive.MemStore
	headReads, selectedReads int
	changeHeadSource         bool
	slowSelected             bool
}

func (s *summaryObservationFault) LookupEnvelope(r archive.Record) (archive.Envelope, bool, error) {
	if r.MessageID == "source" {
		s.headReads++
	}
	if r.MessageID == "next" && s.slowSelected {
		s.selectedReads++
		time.Sleep(6 * time.Second)
	}
	e, found, err := s.MemStore.LookupEnvelope(r)
	if found && r.MessageID == "source" && s.changeHeadSource && s.headReads >= 2 {
		e.Record.Text = "changed previous head source"
	}
	return e, found, err
}
func captureNextSummaryOriginal(t *testing.T, f summaryHTTPFixture) {
	t.Helper()
	body := map[string]any{"project": "p", "provider": "synthetic", "source_instance": "i", "messages": []map[string]any{{"session_id": "s", "message_id": "next", "role": "user", "text": "New synthetic source for automatic extract"}}}
	if code, _ := do(t, http.MethodPost, f.http.URL+"/v1/capture", opHdr(), body); code != 200 {
		t.Fatal("new original", code)
	}
	c := summary.DefaultConfig()
	c.IdleAfter = time.Nanosecond
	if err := f.server.ConfigureSummaries(c, summary.DefaultExtractOptions()); err != nil {
		t.Fatal(err)
	}
}
func TestSummaryWorkerRevalidatesPreviousHeadSourcesAtPublish(t *testing.T) {
	source := &summaryObservationFault{MemStore: archive.NewMemStore()}
	f := newSummaryHTTPFixtureSource(t, source)
	captureNextSummaryOriginal(t, f)
	source.headReads = 0
	source.changeHeadSource = true
	before, _, err := f.control.ArchiveState("p")
	if err != nil {
		t.Fatal(err)
	}
	if count, err := f.server.SummaryOnce(context.Background(), time.Now().UTC()); err == nil || count != 0 {
		t.Fatal("stale head sources advanced progress", count, err)
	}
	after, _, err := f.control.ArchiveState("p")
	if err != nil || after.Pending != nil || after.NextOrdinal != before.NextOrdinal {
		t.Fatal("stale head reserved a new generation", err)
	}
}
func TestSummaryWorkerFinalValidationHasAggregateDeadline(t *testing.T) {
	source := &summaryObservationFault{MemStore: archive.NewMemStore()}
	f := newSummaryHTTPFixtureSource(t, source)
	captureNextSummaryOriginal(t, f)
	source.slowSelected = true
	before, _, err := f.control.ArchiveState("p")
	if err != nil {
		t.Fatal(err)
	}
	count, err := f.server.SummaryOnce(context.Background(), time.Now().UTC())
	if !errors.Is(err, context.DeadlineExceeded) || count != 0 || source.selectedReads != 1 {
		t.Fatal("final deadline did not stop after one in-flight overrun", count, source.selectedReads, err)
	}
	after, _, err := f.control.ArchiveState("p")
	if err != nil || after.Pending != nil || after.NextOrdinal != before.NextOrdinal {
		t.Fatal("expired proof reserved new generation", err)
	}
}
func TestSummaryWorkerRejectsClockRegressionBeforeReservation(t *testing.T) {
	f := newSummaryHTTPFixture(t)
	captureNextSummaryOriginal(t, f)
	before, _, err := f.control.ArchiveState("p")
	if err != nil {
		t.Fatal(err)
	}
	if count, err := f.server.SummaryOnce(context.Background(), time.Now().UTC().Add(time.Hour)); err == nil || count != 0 {
		t.Fatal("future planning clock published", count, err)
	}
	after, _, err := f.control.ArchiveState("p")
	if err != nil || after.Pending != nil || after.NextOrdinal != before.NextOrdinal {
		t.Error("clock/proof error created a new reservation", err)
	}
	if err = f.server.RecoverArchive(); err != nil {
		t.Fatal("safe recovery after proof error", err)
	}
}

type summaryCommitFault struct {
	*archive.MemStore
	fail bool
}

func (s *summaryCommitFault) PutEnvelope(e archive.Envelope) error {
	if s.fail && e.Metadata.DerivedKind == archive.DerivedSessionExtract {
		return errors.New("synthetic derived insert outage")
	}
	return s.MemStore.PutEnvelope(e)
}
func TestSummaryWorkerRecoversFirstDurableBodyWithoutRegeneration(t *testing.T) {
	source := &summaryCommitFault{MemStore: archive.NewMemStore()}
	f := newSummaryHTTPFixtureSource(t, source)
	captureNextSummaryOriginal(t, f)
	source.fail = true
	if count, err := f.server.SummaryOnce(context.Background(), time.Now().UTC()); err == nil || count != 0 {
		t.Fatal("outage reported complete", count, err)
	}
	state, _, err := f.control.ArchiveState("p")
	if err != nil || state.Pending == nil {
		t.Fatal("owned failed generation lost", err)
	}
	first, found, err := f.intake.AcceptedEnvelope(state.Pending.Identity)
	if err != nil || !found {
		t.Fatal("first durable body missing", err)
	}
	source.fail = false
	if _, err = f.server.SummaryOnce(context.Background(), time.Now().UTC()); err != nil {
		t.Fatal("owned recovery", err)
	}
	actual, found, err := source.LookupEnvelope(first.Record)
	if err != nil || !found {
		t.Fatal("recovered source missing", err)
	}
	a, _ := archive.EncodeEnvelope(first)
	b, _ := archive.EncodeEnvelope(actual)
	if string(a) != string(b) {
		t.Fatal("retry changed first durable body/time/ordinal")
	}
	state, _, err = f.control.ArchiveState("p")
	if err != nil || state.Pending != nil || state.CommittedOrdinal != 4 || len(f.control.Budget().Snapshot().Pending) != 0 {
		t.Fatal("recovery left ambiguity", state, err)
	}
}
func TestSummaryWorkerCaptureRegrantKeepsHistoricalHeadAsProgress(t *testing.T) {
	f := newSummaryHTTPFixture(t)
	op := registry.Principal{Kind: registry.Operator}
	for _, enabled := range []bool{false, true} {
		if _, err := f.control.SetConsent(op, "p", "synthetic", "capture", enabled); err != nil {
			t.Fatal(err)
		}
	}
	captureNextSummaryOriginal(t, f)
	if count, err := f.server.SummaryOnce(context.Background(), time.Now().UTC()); err != nil || count != 1 {
		t.Fatal("historical factual head was hidden", count, err)
	}
	state, _, err := f.control.ArchiveState("p")
	if err != nil {
		t.Fatal(err)
	}
	head, found, err := f.store.SummaryHead(archive.SummaryQuery{Project: "p", Provider: "synthetic", Generation: "g", Through: state.CommittedOrdinal, RevokedThrough: 2, CaptureEpoch: 3}, archive.SessionKey{SourceInstance: "i", SessionID: "s"})
	if err != nil || !found {
		t.Fatal(err)
	}
	proof, sources, err := summary.LoadStored(head, f.store, time.Now().UTC())
	if err != nil || proof.Document.Manifest.Progress == nil || proof.Document.Manifest.Progress.AfterOrdinal != 1 || len(sources) != 1 || sources[0].Record.MessageID != "next" || head.Record.ConsentEpoch != 3 {
		t.Fatal("regrant resurrected old capture or reset frontier", err)
	}
}

type summaryScanMutation struct {
	*archive.MemStore
	afterScan func()
}

func (s *summaryScanMutation) ScanSummaryOriginals(q archive.SummaryQuery, key archive.SessionKey, after int64) (archive.EnvelopeWindow, error) {
	page, err := s.MemStore.ScanSummaryOriginals(q, key, after)
	if err == nil && s.afterScan != nil {
		f := s.afterScan
		s.afterScan = nil
		f()
	}
	return page, err
}
func TestSummaryWorkerRechecksRevokeAfterObservationBeforeWAL(t *testing.T) {
	source := &summaryScanMutation{MemStore: archive.NewMemStore()}
	f := newSummaryHTTPFixtureSource(t, source)
	captureNextSummaryOriginal(t, f)
	source.afterScan = func() {
		if _, err := f.control.SetConsent(registry.Principal{Kind: registry.Operator}, "p", "synthetic", "summary", false); err != nil {
			t.Fatal(err)
		}
	}
	before, _, err := f.control.ArchiveState("p")
	if err != nil {
		t.Fatal(err)
	}
	if count, err := f.server.SummaryOnce(context.Background(), time.Now().UTC()); err == nil || count != 0 {
		t.Fatal("post-observation revoke ignored", count, err)
	}
	after, _, err := f.control.ArchiveState("p")
	if err != nil || after.Pending != nil || after.NextOrdinal != before.NextOrdinal {
		t.Fatal("revoked observation reached WAL reservation", err)
	}
}

func TestSummaryWorkerSeparatesIdenticalMessageIDsAcrossSources(t *testing.T) {
	f := newSummaryHTTPFixture(t)
	captureNextSummaryOriginal(t, f)
	body := map[string]any{"project": "p", "provider": "synthetic", "source_instance": "another", "messages": []map[string]any{{"session_id": "s", "message_id": "next", "role": "assistant", "text": "second source marker"}}}
	if code, _ := do(t, http.MethodPost, f.http.URL+"/v1/capture", opHdr(), body); code != 200 {
		t.Fatal(code)
	}
	for n := 0; n < 2; n++ {
		if count, err := f.server.SummaryOnce(context.Background(), time.Now().UTC()); err != nil || count != 1 {
			t.Fatal("independent source generation", count, err)
		}
	}
	state, _, err := f.control.ArchiveState("p")
	if err != nil {
		t.Fatal(err)
	}
	for _, instance := range []string{"another", "i"} {
		head, found, err := f.store.SummaryHead(archive.SummaryQuery{Project: "p", Provider: "synthetic", Generation: "g", Through: state.CommittedOrdinal, CaptureEpoch: 1}, archive.SessionKey{SourceInstance: instance, SessionID: "s"})
		if err != nil || !found {
			t.Fatal("source head missing", instance, err)
		}
		proof, originals, err := summary.LoadStored(head, f.store, time.Now().UTC())
		if err != nil || len(originals) != 1 || originals[0].Record.SourceInstance != instance || originals[0].Record.MessageID != "next" || proof.Document.Manifest.Scope.SourceInstance != instance {
			t.Fatal("source scopes mixed", instance, err)
		}
	}
}
func TestSummaryQueryWithheldExtractPagesRetainCompleteCursorProgress(t *testing.T) {
	f := newSummaryHTTPFixture(t)
	captureNextSummaryOriginal(t, f)
	if _, err := f.server.SummaryOnce(context.Background(), time.Now().UTC()); err != nil {
		t.Fatal(err)
	}
	if _, err := f.control.SetConsent(registry.Principal{Kind: registry.Operator}, "p", "synthetic", "summary", false); err != nil {
		t.Fatal(err)
	}
	cursor := ""
	seen := map[string]bool{}
	emptyContinued := false
	for n := 0; n < 6; n++ {
		path := "/v1/archive/query?project=p"
		if cursor != "" {
			path += "&cursor=" + url.QueryEscape(cursor)
		}
		code, body := agentQuery(t, f.http.URL, path, "summary-reader", f.grantEpoch, "synthetic-reader-secret")
		hits, ok := body["hits"].([]any)
		if code != 200 || !ok {
			t.Fatal("cursor page", code)
		}
		next, _ := body["next_cursor"].(string)
		if len(hits) == 0 && next != "" {
			emptyContinued = true
		}
		for _, hit := range hits {
			r := hit.(map[string]any)
			id := r["MessageID"].(string)
			if r["Type"] != "message" || seen[id] {
				t.Fatal("withheld summary leaked or original repeated", id)
			}
			seen[id] = true
		}
		if next == "" {
			if !emptyContinued || len(seen) != 2 || !seen["source"] || !seen["next"] {
				t.Fatal("incomplete traversal", len(seen), emptyContinued)
			}
			return
		}
		if next == cursor {
			t.Fatal("cursor failed to advance")
		}
		cursor = next
	}
	t.Fatal("cursor traversal never exhausted")
}
func TestUnacceptedReservedExtractProofFailureCancelsSafely(t *testing.T) {
	f := newSummaryHTTPFixture(t)
	captureNextSummaryOriginal(t, f)
	a, _, err := f.control.SummaryActivation("p", "synthetic")
	if err != nil {
		t.Fatal(err)
	}
	before, _, err := f.control.ArchiveState("p")
	if err != nil {
		t.Fatal(err)
	}
	authority := summary.Authority{ConsentEpoch: a.ConsentEpoch, Activation: summary.Baseline{Project: a.Project, Generation: a.Generation, Ordinal: a.Ordinal, At: a.At}}
	c := summary.DefaultConfig()
	c.IdleAfter = time.Nanosecond
	future := time.Now().UTC().Add(time.Hour)
	prepared, err := summary.PrepareSession(f.store, archive.SummaryQuery{Project: "p", Provider: "synthetic", Generation: "g", Through: before.CommittedOrdinal, CaptureEpoch: 1}, archive.SessionKey{SourceInstance: "i", SessionID: "s"}, authority, future, c, summary.DefaultExtractOptions())
	if err != nil || !prepared.Decision.Ready {
		t.Fatal(err)
	}
	record, err := summary.SealExtract(prepared.Document, authority, prepared.Decision.Selected, future)
	if err != nil {
		t.Fatal(err)
	}
	// Arrange the residual clock window through the public reserve/proof seam;
	// no host clock is changed and no source body is accepted after proof failure.
	err = f.control.WithArchiveTransaction(registry.Principal{Kind: registry.Operator}, "p", func(tx *control.ArchiveTransaction) error {
		envelope, err := tx.ReserveSummary(record, a.ConsentEpoch)
		if err != nil {
			return err
		}
		_, err = summary.VerifyStored(envelope, prepared.Decision.Selected, time.Now().UTC())
		return err
	})
	if !errors.Is(err, summary.ErrInvalidStored) {
		t.Fatal("residual proof did not fail", err)
	}
	state, _, err := f.control.ArchiveState("p")
	if err != nil || state.Pending == nil {
		t.Fatal("fixture did not retain reserved intent", err)
	}
	if f.intake.KnownAcceptedIdentity(record) {
		t.Fatal("failed proof accepted source text")
	}
	if err = f.server.RecoverArchive(); err != nil {
		t.Fatal("reserved-only cancellation", err)
	}
	state, _, err = f.control.ArchiveState("p")
	if err != nil || state.Pending != nil || state.CommittedOrdinal != before.CommittedOrdinal || len(f.control.Budget().Snapshot().Pending) != 0 {
		t.Fatal("proof failure changed commitment or stranded intent", err)
	}
	if _, found, err := f.store.LookupEnvelope(record); err != nil || found {
		t.Fatal("unaccepted proof was resurrected", err)
	}
}

// Cancellation at a safe discovery boundary must not start content/proof reads.
type summaryDiscoveryCancel struct {
	*archive.MemStore
	cancel    context.CancelFunc
	headCalls int
}

func (s *summaryDiscoveryCancel) NextSummarySession(q archive.SummaryQuery, after *archive.SessionKey) (archive.SessionKey, bool, error) {
	key, found, err := s.MemStore.NextSummarySession(q, after)
	if s.cancel != nil {
		s.cancel()
	}
	return key, found, err
}
func (s *summaryDiscoveryCancel) SummaryHead(q archive.SummaryQuery, key archive.SessionKey) (archive.Envelope, bool, error) {
	s.headCalls++
	return s.MemStore.SummaryHead(q, key)
}
func TestSummaryWorkerCancellationAfterDiscoveryStartsNoContentRead(t *testing.T) {
	source := &summaryDiscoveryCancel{MemStore: archive.NewMemStore()}
	f := newSummaryHTTPFixtureSource(t, source)
	captureNextSummaryOriginal(t, f)
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	source.cancel = cancel
	count, err := f.server.SummaryOnce(ctx, time.Now().UTC())
	if !errors.Is(err, context.Canceled) || count != 0 || source.headCalls != 0 {
		t.Fatal("cancellation started new proof IO", count, err, source.headCalls)
	}
}

type summaryRecoveryCancel struct {
	*archive.MemStore
	fail           bool
	cancel         context.CancelFunc
	discoveryCalls int
}

func (s *summaryRecoveryCancel) PutEnvelope(e archive.Envelope) error {
	if e.Metadata.DerivedKind == archive.DerivedSessionExtract {
		if s.fail {
			return errors.New("synthetic derived insert outage")
		}
		if s.cancel != nil {
			s.cancel()
		}
	}
	return s.MemStore.PutEnvelope(e)
}
func (s *summaryRecoveryCancel) NextSummarySession(q archive.SummaryQuery, after *archive.SessionKey) (archive.SessionKey, bool, error) {
	s.discoveryCalls++
	return s.MemStore.NextSummarySession(q, after)
}
func TestSummaryWorkerCancellationDuringRecoveryStartsNoDiscovery(t *testing.T) {
	source := &summaryRecoveryCancel{MemStore: archive.NewMemStore()}
	f := newSummaryHTTPFixtureSource(t, source)
	captureNextSummaryOriginal(t, f)
	source.fail = true
	if _, err := f.server.SummaryOnce(context.Background(), time.Now().UTC()); err == nil {
		t.Fatal("expected synthetic failure")
	}
	source.fail = false
	source.discoveryCalls = 0
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	source.cancel = cancel
	count, err := f.server.SummaryOnce(ctx, time.Now().UTC())
	if !errors.Is(err, context.Canceled) || count != 0 || source.discoveryCalls != 0 {
		t.Fatal("recovery cancellation started new discovery", count, err, source.discoveryCalls)
	}
}

type summaryBoundarySource struct {
	*archive.MemStore
	missingSchema      bool
	discoveries, heads int
	afterDiscovery     func()
}

func (s *summaryBoundarySource) SummarySchemaReady() (bool, error) {
	if s.missingSchema {
		return false, nil
	}
	return s.MemStore.SummarySchemaReady()
}
func (s *summaryBoundarySource) NextSummarySession(q archive.SummaryQuery, k *archive.SessionKey) (archive.SessionKey, bool, error) {
	s.discoveries++
	key, found, err := s.MemStore.NextSummarySession(q, k)
	if s.afterDiscovery != nil {
		f := s.afterDiscovery
		s.afterDiscovery = nil
		f()
	}
	return key, found, err
}
func (s *summaryBoundarySource) SummaryHead(q archive.SummaryQuery, k archive.SessionKey) (archive.Envelope, bool, error) {
	s.heads++
	return s.MemStore.SummaryHead(q, k)
}
func TestSummaryWorkerRequiresSchemaAndSingleConfiguration(t *testing.T) {
	for _, kind := range []string{"schema", "once"} {
		t.Run(kind, func(t *testing.T) {
			source := &summaryBoundarySource{MemStore: archive.NewMemStore()}
			f := newSummaryHTTPFixtureSource(t, source)
			if kind == "once" {
				if err := f.server.ConfigureSummaries(summary.DefaultConfig(), summary.DefaultExtractOptions()); err != nil {
					t.Fatal(err)
				}
			} else {
				source.missingSchema = true
			}
			if err := f.server.ConfigureSummaries(summary.DefaultConfig(), summary.DefaultExtractOptions()); err == nil {
				t.Fatal("unsupported worker configuration accepted", kind)
			}
		})
	}
}
func TestSummaryWorkerRejectsBackwardSecondTick(t *testing.T) {
	f := newSummaryHTTPFixture(t)
	if err := f.server.ConfigureSummaries(summary.DefaultConfig(), summary.DefaultExtractOptions()); err != nil {
		t.Fatal(err)
	}
	first := time.Now().UTC().Add(time.Minute)
	if n, err := f.server.SummaryOnce(context.Background(), first); err != nil || n != 0 {
		t.Fatal("first unchanged tick", n, err)
	}
	if n, err := f.server.SummaryOnce(context.Background(), first.Add(-time.Second)); err == nil || n != 0 {
		t.Fatal("backward second tick accepted", n, err)
	}
}
func TestSummaryWorkerPreReadBarriersAndPendingReservation(t *testing.T) {
	for _, kind := range []string{"project-barrier", "session-barrier", "pending"} {
		t.Run(kind, func(t *testing.T) {
			source := &summaryBoundarySource{MemStore: archive.NewMemStore()}
			f := newSummaryHTTPFixtureSource(t, source)
			captureNextSummaryOriginal(t, f)
			op := registry.Principal{Kind: registry.Operator}
			switch kind {
			case "project-barrier":
				if _, err := f.control.DeleteProjectBarrier(op, "p"); err != nil {
					t.Fatal(err)
				}
			case "session-barrier":
				if _, err := f.control.DeleteSessionBarrier(op, "p", "s"); err != nil {
					t.Fatal(err)
				}
			case "pending":
				source.afterDiscovery = func() {
					r := f.original.Record
					r.MessageID = "pending-after-discovery"
					if err := f.control.WithArchiveTransaction(op, "p", func(tx *control.ArchiveTransaction) error { _, err := tx.Reserve(r, nil, false); return err }); err != nil {
						t.Error(err)
					}
				}
			}
			_, err := f.server.SummaryOnce(context.Background(), time.Now().UTC())
			if kind == "pending" && err == nil {
				t.Fatal("pending source was not refused")
			}
			if source.heads != 0 || (kind == "project-barrier" && source.discoveries != 0) {
				t.Fatal("blocked worker started content/discovery IO", kind, source.heads, source.discoveries)
			}
		})
	}
}
func TestSummaryWorkerPolicyRevisionChangesRequireReobservation(t *testing.T) {
	for _, stage := range []string{"discovery", "observation"} {
		t.Run(stage, func(t *testing.T) {
			op := registry.Principal{Kind: registry.Operator}
			var f summaryHTTPFixture
			var source *summaryBoundarySource
			var scan *summaryScanMutation
			if stage == "discovery" {
				source = &summaryBoundarySource{MemStore: archive.NewMemStore()}
				f = newSummaryHTTPFixtureSource(t, source)
			} else {
				scan = &summaryScanMutation{MemStore: archive.NewMemStore()}
				f = newSummaryHTTPFixtureSource(t, scan)
			}
			captureNextSummaryOriginal(t, f)
			change := func() {
				if _, err := f.control.SetConsent(op, "p", "unrelated-provider", "capture", true); err != nil {
					t.Error(err)
				}
			}
			if source != nil {
				source.afterDiscovery = change
			} else {
				scan.afterScan = change
			}
			before, _, err := f.control.ArchiveState("p")
			if err != nil {
				t.Fatal(err)
			}
			if n, err := f.server.SummaryOnce(context.Background(), time.Now().UTC()); err == nil || n != 0 {
				t.Fatal("policy revision change published stale observation", stage, n, err)
			}
			after, _, err := f.control.ArchiveState("p")
			if err != nil || after.Pending != nil || before.NextOrdinal != after.NextOrdinal {
				t.Fatal("changed policy reserved source", stage, err)
			}
			if source != nil && source.heads != 0 {
				t.Fatal("discovery policy change started content reads", source.heads)
			}
		})
	}
}

type summaryLostHeadSource struct {
	*archive.MemStore
	previous archive.Envelope
	hide     bool
}

func (s *summaryLostHeadSource) SummaryHead(q archive.SummaryQuery, k archive.SessionKey) (archive.Envelope, bool, error) {
	if s.hide {
		return s.previous, true, nil
	}
	return s.MemStore.SummaryHead(q, k)
}
func (s *summaryLostHeadSource) LookupEnvelope(r archive.Record) (archive.Envelope, bool, error) {
	if s.hide && r.Type == archive.TypeSummary && r.MessageID != s.previous.Record.MessageID {
		return archive.Envelope{}, false, nil
	}
	return s.MemStore.LookupEnvelope(r)
}
func TestSummaryWorkerDoesNotRegenerateAcceptedJobAfterSourceLoss(t *testing.T) {
	source := &summaryLostHeadSource{MemStore: archive.NewMemStore()}
	f := newSummaryHTTPFixtureSource(t, source)
	var err error
	source.previous, _, err = source.MemStore.LookupEnvelope(f.record)
	if err != nil {
		t.Fatal(err)
	}
	captureNextSummaryOriginal(t, f)
	if n, err := f.server.SummaryOnce(context.Background(), time.Now().UTC()); err != nil || n != 1 {
		t.Fatal("initial durable generation", n, err)
	}
	before, _, err := f.control.ArchiveState("p")
	if err != nil {
		t.Fatal(err)
	}
	accepted := summaryAcceptedCount(t, f.intake)
	source.hide = true
	refused := false
	for n := 0; n < 2; n++ {
		count, err := f.server.SummaryOnce(context.Background(), time.Now().UTC())
		if count != 0 {
			t.Fatal("accepted job regenerated", count)
		}
		refused = refused || err != nil
	}
	after, _, err := f.control.ArchiveState("p")
	if err != nil || !refused || after.Pending != nil || after.NextOrdinal != before.NextOrdinal || summaryAcceptedCount(t, f.intake) != accepted {
		t.Fatal("lost accepted source created new reservation/WAL", refused, err)
	}
}
func TestSummaryWorkerLegacyReservedIdentityCollisionPrecedesReservation(t *testing.T) {
	f := newSummaryHTTPFixture(t)
	captureNextSummaryOriginal(t, f)
	a, found, err := f.control.SummaryActivation("p", "synthetic")
	if err != nil || !found {
		t.Fatal(err)
	}
	state, _, err := f.control.ArchiveState("p")
	if err != nil {
		t.Fatal(err)
	}
	c := summary.DefaultConfig()
	c.IdleAfter = time.Nanosecond
	now := time.Now().UTC()
	authority := summary.Authority{ConsentEpoch: a.ConsentEpoch, Activation: summary.Baseline{Project: a.Project, Generation: a.Generation, Ordinal: a.Ordinal, At: a.At}}
	prepared, err := summary.PrepareSession(f.store, archive.SummaryQuery{Project: "p", Provider: "synthetic", Generation: "g", Through: state.CommittedOrdinal, CaptureEpoch: 1}, archive.SessionKey{SourceInstance: "i", SessionID: "s"}, authority, now, c, summary.DefaultExtractOptions())
	if err != nil || !prepared.Decision.Ready {
		t.Fatal(err)
	}
	record, err := summary.SealExtract(prepared.Document, authority, prepared.Decision.Selected, now)
	if err != nil {
		t.Fatal(err)
	}
	record.Text = "historical unmarked manual identity collision"
	if err = f.store.Put(record); err != nil {
		t.Fatal(err)
	}
	accepted := summaryAcceptedCount(t, f.intake)
	if count, err := f.server.SummaryOnce(context.Background(), time.Now().UTC()); err == nil || count != 0 {
		t.Fatal("existing identity not refused", count, err)
	}
	after, _, err := f.control.ArchiveState("p")
	if err != nil || after.Pending != nil || after.NextOrdinal != state.NextOrdinal || summaryAcceptedCount(t, f.intake) != accepted {
		t.Fatal("identity collision poisoned reservation/WAL", err)
	}
}

type summaryHeadSwapSource struct {
	*archive.MemStore
	replacement archive.Envelope
	missing     bool
	headReads   int
}

func (s *summaryHeadSwapSource) SummaryHead(q archive.SummaryQuery, k archive.SessionKey) (archive.Envelope, bool, error) {
	s.headReads++
	if s.headReads == 2 {
		if s.missing {
			return archive.Envelope{}, false, nil
		}
		return s.replacement, true, nil
	}
	return s.MemStore.SummaryHead(q, k)
}
func TestSummaryWorkerRejectsHeadReplacementBeforePublish(t *testing.T) {
	for _, kind := range []string{"missing", "different-valid-proof"} {
		t.Run(kind, func(t *testing.T) {
			source := &summaryHeadSwapSource{MemStore: archive.NewMemStore(), missing: kind == "missing"}
			f := newSummaryHTTPFixtureSource(t, source)
			captureNextSummaryOriginal(t, f)
			a, _, err := f.control.SummaryActivation("p", "synthetic")
			if err != nil {
				t.Fatal(err)
			}
			baseline := summary.Baseline{Project: a.Project, Generation: a.Generation, Ordinal: a.Ordinal, At: a.At}
			c := summary.DefaultConfig()
			c.IdleAfter = time.Nanosecond
			o := summary.DefaultExtractOptions()
			o.MaxExcerptBytes = 3
			now := time.Now().UTC()
			in := summary.Input{Scope: summary.Scope{Project: "p", Provider: "synthetic", SourceInstance: "i", SessionID: "s"}, Generation: "g", Cutoff: 1, Complete: true, Activation: &baseline, Messages: []archive.Envelope{f.original}}
			doc, decision, err := summary.GenerateExtract(c, now, in, o)
			if err != nil || !decision.Ready {
				t.Fatal(err)
			}
			record, err := summary.SealExtract(doc, summary.Authority{ConsentEpoch: a.ConsentEpoch, Activation: baseline}, in.Messages, now)
			if err != nil {
				t.Fatal(err)
			}
			source.replacement = archive.Envelope{Version: 2, Record: record, Metadata: archive.Metadata{Generation: "g", Ordinal: 2, CapturedAt: &now, DerivedKind: archive.DerivedSessionExtract}}
			if _, _, err = summary.LoadStored(source.replacement, source, now); err != nil {
				t.Fatal("replacement proof fixture invalid", err)
			}
			before, _, err := f.control.ArchiveState("p")
			if err != nil {
				t.Fatal(err)
			}
			if count, err := f.server.SummaryOnce(context.Background(), time.Now().UTC()); err == nil || count != 0 {
				t.Fatal("changed newest head published stale progress", kind, count, err)
			}
			after, _, err := f.control.ArchiveState("p")
			if err != nil || after.Pending != nil || before.NextOrdinal != after.NextOrdinal {
				t.Fatal("head change reserved source", kind, err)
			}
		})
	}
}

type summaryRawPageCounter struct {
	*archive.MemStore
	summaries map[string]int
}

func (s *summaryRawPageCounter) LookupEnvelope(r archive.Record) (archive.Envelope, bool, error) {
	if r.Type == archive.TypeSummary && s.summaries != nil {
		s.summaries[r.MessageID]++
	}
	return s.MemStore.LookupEnvelope(r)
}
func TestSummaryQueryCursorConsumesWithheldRawPositionAfterVisibleHit(t *testing.T) {
	source := &summaryRawPageCounter{MemStore: archive.NewMemStore()}
	f := newSummaryHTTPFixtureSource(t, source)
	body := map[string]any{"project": "p", "provider": "synthetic", "source_instance": "i", "messages": []map[string]any{{"session_id": "s", "message_id": "00-before", "role": "user", "text": "synthetic before withheld raw position"}}}
	if code, _ := do(t, http.MethodPost, f.http.URL+"/v1/capture", opHdr(), body); code != 200 {
		t.Fatal(code)
	}
	c := summary.DefaultConfig()
	c.IdleAfter = time.Nanosecond
	if err := f.server.ConfigureSummaries(c, summary.DefaultExtractOptions()); err != nil {
		t.Fatal(err)
	}
	if n, err := f.server.SummaryOnce(context.Background(), time.Now().UTC()); err != nil || n != 1 {
		t.Fatal(n, err)
	}
	if _, err := f.control.SetConsent(registry.Principal{Kind: registry.Operator}, "p", "synthetic", "summary", false); err != nil {
		t.Fatal(err)
	}
	source.summaries = map[string]int{}
	seen := map[string]bool{}
	cursor := ""
	exhausted := false
	for n := 0; n < 6; n++ {
		path := "/v1/archive/query?project=p"
		if cursor != "" {
			path += "&cursor=" + url.QueryEscape(cursor)
		}
		code, body := agentQuery(t, f.http.URL, path, "summary-reader", f.grantEpoch, "synthetic-reader-secret")
		hits, ok := body["hits"].([]any)
		if code != 200 || !ok {
			t.Fatal(code, body)
		}
		for _, hit := range hits {
			id := hit.(map[string]any)["MessageID"].(string)
			if seen[id] {
				t.Fatal("visible hit repeated", id)
			}
			seen[id] = true
		}
		next, _ := body["next_cursor"].(string)
		if next == "" {
			exhausted = true
			break
		}
		if next == cursor {
			t.Fatal("cursor cycle")
		}
		cursor = next
	}
	if !exhausted || len(seen) != 2 || !seen["00-before"] || !seen["source"] || len(source.summaries) != 2 {
		t.Fatal("raw traversal incomplete", exhausted, len(seen), source.summaries)
	}
	for id, count := range source.summaries {
		if count != 1 {
			t.Fatal("consumed withheld raw position reread", id, count)
		}
	}
}
func TestSummaryContextReportsDerivedAnchorStop(t *testing.T) {
	f := newSummaryHTTPFixture(t)
	path := strings.Replace(messagePath(f.record), "/message?", "/context?", 1)
	code, body := agentQuery(t, f.http.URL, path, "summary-reader", f.grantEpoch, "synthetic-reader-secret")
	records, ok := body["records"].([]any)
	if code != 200 || !ok || len(records) != 1 || body["derived"] != true || body["incomplete"] != true || body["stop_reason"] != "derived_record" {
		t.Fatal("derived anchor implies original parent chain", code, body)
	}
}
