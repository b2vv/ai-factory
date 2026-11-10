package api_test

import (
	"aifactory.local/storage/internal/api"
	"aifactory.local/storage/internal/archive"
	"aifactory.local/storage/internal/budget"
	"aifactory.local/storage/internal/control"
	"aifactory.local/storage/internal/ingest"
	"aifactory.local/storage/internal/registry"
	"aifactory.local/storage/internal/summary"
	"encoding/json"
	"errors"
	"io"
	"net/http"
	"net/http/httptest"
	"net/url"
	"path/filepath"
	"reflect"
	"strings"
	"testing"
	"time"
)

type summaryFixtureSource interface {
	archive.Store
	archive.SummarySource
}

type summaryHTTPFixture struct {
	intake     *ingest.Ingestor
	original   archive.Envelope
	store      summaryFixtureSource
	server     *api.Server
	http       *httptest.Server
	control    *control.Durable
	record     archive.Record
	grantEpoch string
}

func newSummaryHTTPFixture(t *testing.T) summaryHTTPFixture {
	return newSummaryHTTPFixtureSource(t, archive.NewMemStore())
}

func newSummaryHTTPFixtureSource(t *testing.T, store summaryFixtureSource) summaryHTTPFixture {
	t.Helper()
	return newSummaryHTTPFixturePair(t, store, false)
}
func newSummaryHTTPFixturePair(t *testing.T, store summaryFixtureSource, pair bool) summaryHTTPFixture {
	t.Helper()
	ts, srv, intake, ctl := captureServer(t, store, nil)
	op := registry.Principal{Kind: registry.Operator}
	if err := ctl.MintProject(op, "p", "synthetic"); err != nil {
		t.Fatal(err)
	}
	if _, err := ctl.SetConsent(op, "p", "synthetic", "capture", true); err != nil {
		t.Fatal(err)
	}
	if err := ctl.BeginArchiveMigration(op, "p", "g"); err != nil {
		t.Fatal(err)
	}
	root := t.TempDir()
	ledger, err := budget.Initialize(filepath.Join(root, "budget.bin"), budget.Policy{LiveCap: 1 << 30}, func() (budget.Sample, error) { return budget.LocalSample(root, 1<<30) })
	if err != nil {
		t.Fatal(err)
	}
	if err = ctl.AttachBudget(ledger); err != nil {
		t.Fatal(err)
	}
	if err = intake.SetBudget(ledger); err != nil {
		t.Fatal(err)
	}
	if err = ctl.WithArchiveTransaction(op, "p", func(tx *control.ArchiveTransaction) error {
		return tx.FinishMigration(func(control.ArchiveState) error { return nil })
	}); err != nil {
		t.Fatal(err)
	}
	epoch, err := ctl.SetConsent(op, "p", "synthetic", "summary", true)
	if err != nil {
		t.Fatal(err)
	}
	activation, found, err := ctl.SummaryActivation("p", "synthetic")
	if err != nil || !found {
		t.Fatal(err)
	}
	var original archive.Envelope
	r := archive.Record{Project: "p", Provider: "synthetic", SourceInstance: "i", SessionID: "s", MessageID: "source", Type: archive.TypeMessage, Role: "user", Text: "Synthetic\nlocal\x00extract privacy fixture", ConsentEpoch: 1}
	if err = ctl.WithArchiveTransaction(op, "p", func(tx *control.ArchiveTransaction) error {
		original, err = tx.Reserve(r, nil, false)
		if err != nil {
			return err
		}
		_, err = intake.CommitEnvelope(tx, original)
		return err
	}); err != nil {
		t.Fatal(err)
	}
	originals := []archive.Envelope{original}
	if pair {
		secondRecord := r
		secondRecord.MessageID = "source-two"
		secondRecord.Role = "assistant"
		secondRecord.Text = "Second excerpt with a distinct boundary"
		var second archive.Envelope
		if err = ctl.WithArchiveTransaction(op, "p", func(tx *control.ArchiveTransaction) error {
			var e error
			second, e = tx.Reserve(secondRecord, nil, false)
			if e != nil {
				return e
			}
			_, e = intake.CommitEnvelope(tx, second)
			return e
		}); err != nil {
			t.Fatal(err)
		}
		originals = append(originals, second)
	}
	config := summary.DefaultConfig()
	config.IdleAfter = time.Nanosecond
	baseline := summary.Baseline{Project: "p", Generation: "g", Ordinal: activation.Ordinal, At: activation.At}
	in := summary.Input{Scope: summary.Scope{Project: "p", Provider: "synthetic", SourceInstance: "i", SessionID: "s"}, Generation: "g", Cutoff: int64(len(originals)), Complete: true, Activation: &baseline, Messages: originals}
	now := time.Now().UTC()
	document, decision, err := summary.GenerateExtract(config, now, in, summary.DefaultExtractOptions())
	if err != nil || !decision.Ready {
		t.Fatal("fixture generation", decision, err)
	}
	record, err := summary.SealExtract(document, summary.Authority{ConsentEpoch: epoch, Activation: baseline}, in.Messages, now)
	if err != nil {
		t.Fatal(err)
	}
	if err = ctl.WithArchiveTransaction(op, "p", func(tx *control.ArchiveTransaction) error {
		derived, e := tx.ReserveSummary(record, epoch)
		if e != nil {
			return e
		}
		_, e = intake.CommitEnvelope(tx, derived)
		return e
	}); err != nil {
		t.Fatal(err)
	}
	_, grant := do(t, http.MethodPost, ts.URL+"/v1/grants", opHdr(), map[string]any{"principal_id": "summary-reader", "kind": "agent", "projects": []string{"p"}, "ops": []string{"archive.query", "search"}, "secret": "synthetic-reader-secret"})
	grantEpoch := itoa(int64(grant["epoch"].(float64)))
	return summaryHTTPFixture{intake: intake, original: original, store: store, server: srv, http: ts, control: ctl, record: record, grantEpoch: grantEpoch}
}

func TestArchiveMessageWithholdsExtractImmediatelyAfterSummaryRevoke(t *testing.T) {
	f := newSummaryHTTPFixture(t)
	store, ts, ctl, record, grantEpoch := f.store, f.http, f.control, f.record, f.grantEpoch
	original := f.original
	op := registry.Principal{Kind: registry.Operator}
	var err error

	if code, body := agentQuery(t, ts.URL, messagePath(record), "summary-reader", grantEpoch, "synthetic-reader-secret"); code != 200 {
		t.Fatal("valid extract unavailable", code, body)
	}

	t.Run("query-matches-excerpts-not-proof-wrapper", func(t *testing.T) {
		code, body := agentQuery(t, ts.URL, "/v1/archive/query?project=p&q=ai-factory.stored-session-extract", "summary-reader", grantEpoch, "synthetic-reader-secret")
		hits, ok := body["hits"].([]any)
		if code != 200 || !ok || len(hits) != 0 {
			t.Fatal("proof metadata was searchable content", code, body)
		}
	})
	if _, err = ctl.SetConsent(op, "p", "synthetic", "summary", false); err != nil {
		t.Fatal(err)
	}
	if code, _ := agentQuery(t, ts.URL, messagePath(record), "summary-reader", grantEpoch, "synthetic-reader-secret"); code != 404 {
		t.Fatal("revoked derived text remained visible", code)
	}

	t.Run("query-withholds-revoked-extract", func(t *testing.T) {
		code, body := agentQuery(t, ts.URL, "/v1/archive/query?project=p", "summary-reader", grantEpoch, "synthetic-reader-secret")
		hits, ok := body["hits"].([]any)
		if code != 200 || !ok || len(hits) != 1 {
			t.Fatal("query leaked revoked extract", code, body)
		}
	})
	t.Run("context-withholds-revoked-extract", func(t *testing.T) {
		path := strings.Replace(messagePath(record), "/message?", "/context?", 1)
		if code, _ := agentQuery(t, ts.URL, path, "summary-reader", grantEpoch, "synthetic-reader-secret"); code != 404 {
			t.Fatal("context leaked revoked extract", code)
		}
	})
	// Ordinary/manual summaries keep their existing capture policy semantics.
	manual := original.Record
	manual.MessageID = "manual"
	manual.Type = archive.TypeSummary
	if err = store.Put(manual); err != nil {
		t.Fatal(err)
	}
	if code, _ := agentQuery(t, ts.URL, messagePath(manual), "summary-reader", grantEpoch, "synthetic-reader-secret"); code != 200 {
		t.Fatal("manual summary incorrectly classified", code)
	}
}

type summaryProofReadFault struct {
	*archive.MemStore
	fail, missing, changed            bool
	missingSummary, mismatchedSummary bool
	afterRead                         func()
}

func (s *summaryProofReadFault) LookupEnvelope(r archive.Record) (archive.Envelope, bool, error) {
	e, found, err := s.MemStore.LookupEnvelope(r)
	if r.Type == archive.TypeSummary {
		if s.missingSummary {
			return archive.Envelope{}, false, nil
		}
		if s.mismatchedSummary {
			e.Record.Text = "mismatched metadata envelope"
		}
	}
	if r.MessageID == "source" {
		if s.fail {
			return archive.Envelope{}, false, errors.New("PRIVATE_COVERED_SOURCE_CANARY")
		}
		if s.missing {
			return archive.Envelope{}, false, nil
		}
		if s.changed {
			e.Record.Text = "changed factual source"
		}
		if s.afterRead != nil {
			f := s.afterRead
			s.afterRead = nil
			f()
		}
	}
	return e, found, err
}
func TestSummaryCoveredSourceFailureDoesNotLeakAndRemainsRetryable(t *testing.T) {
	source := &summaryProofReadFault{MemStore: archive.NewMemStore()}
	f := newSummaryHTTPFixtureSource(t, source)
	paths := []string{messagePath(f.record), strings.Replace(messagePath(f.record), "/message?", "/context?", 1), "/v1/archive/query?project=p"}
	source.fail = true
	for _, path := range paths {
		req, err := http.NewRequest(http.MethodGet, f.http.URL+path, nil)
		if err != nil {
			t.Fatal(err)
		}
		req.Header.Set("X-Principal-Id", "summary-reader")
		req.Header.Set("X-Grant-Epoch", f.grantEpoch)
		req.Header.Set("X-Secret", "synthetic-reader-secret")
		response, err := (&http.Client{Timeout: 5 * time.Second}).Do(req)
		if err != nil {
			t.Fatal(err)
		}
		raw, err := io.ReadAll(io.LimitReader(response.Body, 8193))
		response.Body.Close()
		if err != nil || response.StatusCode != 503 || strings.Contains(string(raw), "PRIVATE_") || len(raw) > 8192 || !json.Valid(raw) {
			t.Fatal("proof outage leaked or looked like absence", response.StatusCode, string(raw), err)
		}
	}
	source.fail = false
	if code, _ := agentQuery(t, f.http.URL, messagePath(f.record), "summary-reader", f.grantEpoch, "synthetic-reader-secret"); code != 200 {
		t.Fatal("transient proof failure not retryable", code)
	}
	for _, kind := range []string{"missing", "changed"} {
		source.missing = kind == "missing"
		source.changed = kind == "changed"
		if code, body := agentQuery(t, f.http.URL, messagePath(f.record), "summary-reader", f.grantEpoch, "synthetic-reader-secret"); code != 404 || !reflect.DeepEqual(body, map[string]any{"error": "not_found"}) {
			t.Fatal("invalid proof distinguishable from absence", kind, code, body)
		}
	}
}
func TestSummaryAuthorityIsRecheckedAfterCoveredSourceRead(t *testing.T) {
	for _, kind := range []string{"summary-revoke", "covered-session-barrier"} {
		t.Run(kind, func(t *testing.T) {
			source := &summaryProofReadFault{MemStore: archive.NewMemStore()}
			f := newSummaryHTTPFixtureSource(t, source)
			op := registry.Principal{Kind: registry.Operator}
			source.afterRead = func() {
				if kind == "summary-revoke" {
					if _, err := f.control.SetConsent(op, "p", "synthetic", "summary", false); err != nil {
						t.Error(err)
					}
				} else {
					if _, err := f.control.DeleteSessionBarrier(op, "p", "s"); err != nil {
						t.Error(err)
					}
				}
			}
			if code, body := agentQuery(t, f.http.URL, messagePath(f.record), "summary-reader", f.grantEpoch, "synthetic-reader-secret"); code != 404 {
				t.Fatal("post-read authority change leaked derived content", kind, code, body)
			}
		})
	}
}

func TestSummaryMissingOrMismatchedEnvelopeIsWithheldBeforeMarkerClassification(t *testing.T) {
	for _, kind := range []string{"missing", "mismatched"} {
		t.Run(kind, func(t *testing.T) {
			source := &summaryProofReadFault{MemStore: archive.NewMemStore()}
			f := newSummaryHTTPFixtureSource(t, source)
			source.missingSummary = kind == "missing"
			source.mismatchedSummary = kind == "mismatched"
			if code, body := agentQuery(t, f.http.URL, messagePath(f.record), "summary-reader", f.grantEpoch, "synthetic-reader-secret"); code != 404 || !reflect.DeepEqual(body, map[string]any{"error": "not_found"}) {
				t.Fatal("missing metadata treated as manual summary", kind, code, body)
			}
		})
	}
}

func TestSummaryQueryJoinsMultipleExcerptsWithHonestSnippetBasis(t *testing.T) {
	f := newSummaryHTTPFixturePair(t, archive.NewMemStore(), true)
	needle := "fixture\nSecond"
	code, body := agentQuery(t, f.http.URL, "/v1/archive/query?project=p&q="+url.QueryEscape(needle), "summary-reader", f.grantEpoch, "synthetic-reader-secret")
	hits, ok := body["hits"].([]any)
	if code != 200 || !ok || len(hits) != 1 {
		t.Fatal("literal excerpt boundary not searchable", code, body)
	}
	hit, ok := hits[0].(map[string]any)
	if !ok || hit["MessageID"] != f.record.MessageID {
		t.Fatal("expected only derived cross-excerpt hit", hits)
	}
	snippets, ok := body["snippets"].([]any)
	if !ok || len(snippets) != 1 {
		t.Fatal("missing derived snippet", body)
	}
	snippet, ok := snippets[0].(map[string]any)
	if !ok || snippet["basis"] != "verified_extract_text:literal_match" || snippet["match"] != true || !strings.Contains(snippet["text"].(string), needle) {
		t.Fatal("snippet basis or literal boundary false", snippet)
	}
}
