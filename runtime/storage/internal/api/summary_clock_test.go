package api

import (
	"aifactory.local/storage/internal/archive"
	"aifactory.local/storage/internal/budget"
	"aifactory.local/storage/internal/config"
	"aifactory.local/storage/internal/control"
	"aifactory.local/storage/internal/ingest"
	"aifactory.local/storage/internal/registry"
	"aifactory.local/storage/internal/summary"
	"encoding/json"
	"errors"
	"net/http"
	"net/http/httptest"
	"net/url"
	"path/filepath"
	"reflect"
	"strings"
	"testing"
	"time"
)

type summaryClockStore struct {
	*archive.MemStore
	failDerived   bool
	derivedWrites int
}

func (s *summaryClockStore) PutEnvelope(e archive.Envelope) error {
	if e.Metadata.DerivedKind == archive.DerivedSessionExtract {
		s.derivedWrites++
		if s.failDerived {
			return errors.New("synthetic derived insert outage")
		}
	}
	return s.MemStore.PutEnvelope(e)
}

type summaryClockFixture struct {
	server   *Server
	control  *control.Durable
	intake   *ingest.Ingestor
	source   *summaryClockStore
	envelope archive.Envelope
	op       registry.Principal
}

func newSummaryClockFixture(t *testing.T, pending bool) summaryClockFixture {
	t.Helper()
	root := t.TempDir()
	d, err := control.Initialize(filepath.Join(root, "control"))
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { d.Close() })
	op := registry.Principal{Kind: registry.Operator}
	if err = d.MintProject(op, "p", "synthetic"); err != nil {
		t.Fatal(err)
	}
	if _, err = d.SetConsent(op, "p", "synthetic", "capture", true); err != nil {
		t.Fatal(err)
	}
	if err = d.BeginArchiveMigration(op, "p", "g"); err != nil {
		t.Fatal(err)
	}
	source := &summaryClockStore{MemStore: archive.NewMemStore()}
	i, err := ingest.Open(filepath.Join(root, "ingest"), config.NewAccountant(config.Default()), source)
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { i.Close() })
	ledger, err := budget.Initialize(filepath.Join(root, "budget"), budget.Policy{LiveCap: 1 << 30}, func() (budget.Sample, error) { return budget.LocalSample(root, 1<<30) })
	if err != nil {
		t.Fatal(err)
	}
	if err = d.AttachBudget(ledger); err != nil {
		t.Fatal(err)
	}
	if err = i.SetBudget(ledger); err != nil {
		t.Fatal(err)
	}
	if err = d.WithArchiveTransaction(op, "p", func(tx *control.ArchiveTransaction) error {
		return tx.FinishMigration(func(control.ArchiveState) error { return nil })
	}); err != nil {
		t.Fatal(err)
	}
	epoch, err := d.SetConsent(op, "p", "synthetic", "summary", true)
	if err != nil {
		t.Fatal(err)
	}
	a, _, err := d.SummaryActivation("p", "synthetic")
	if err != nil {
		t.Fatal(err)
	}
	r := archive.Record{Project: "p", Provider: "synthetic", SourceInstance: "i", SessionID: "s", MessageID: "source", Role: "user", Type: archive.TypeMessage, Text: "synthetic clock fixture source", ConsentEpoch: 1}
	var original archive.Envelope
	if err = d.WithArchiveTransaction(op, "p", func(tx *control.ArchiveTransaction) error {
		var e error
		original, e = tx.Reserve(r, nil, false)
		if e != nil {
			return e
		}
		_, e = i.CommitEnvelope(tx, original)
		return e
	}); err != nil {
		t.Fatal(err)
	}
	baseline := summary.Baseline{Project: a.Project, Generation: a.Generation, Ordinal: a.Ordinal, At: a.At}
	c := summary.DefaultConfig()
	c.IdleAfter = time.Nanosecond
	now := time.Now().UTC()
	in := summary.Input{Scope: summary.Scope{Project: "p", Provider: "synthetic", SourceInstance: "i", SessionID: "s"}, Generation: "g", Cutoff: 1, Complete: true, Activation: &baseline, Messages: []archive.Envelope{original}}
	doc, decision, err := summary.GenerateExtract(c, now, in, summary.DefaultExtractOptions())
	if err != nil || !decision.Ready {
		t.Fatal(err)
	}
	record, err := summary.SealExtract(doc, summary.Authority{ConsentEpoch: epoch, Activation: baseline}, in.Messages, now)
	if err != nil {
		t.Fatal(err)
	}
	source.failDerived = pending
	var envelope archive.Envelope
	err = d.WithArchiveTransaction(op, "p", func(tx *control.ArchiveTransaction) error {
		var e error
		envelope, e = tx.ReserveSummary(record, epoch)
		if e != nil {
			return e
		}
		_, e = i.CommitEnvelope(tx, envelope)
		return e
	})
	if (err != nil) != pending {
		t.Fatal("fixture pending source phase", pending, err)
	}
	accepted, found, err := i.AcceptedEnvelope(record)
	if err != nil || !found || !reflect.DeepEqual(accepted, envelope) {
		t.Fatal("fixture did not accept first exact body", found, err)
	}
	cfg := config.Default()
	s := New(d, cfg, "op", "synthetic-clock-operator")
	s.SetIngestor(i)
	return summaryClockFixture{s, d, i, source, envelope, op}
}
func TestSummaryAcceptedWALClockRegressionRetainsFirstBody(t *testing.T) {
	f := newSummaryClockFixture(t, true)
	// Dependency is configured before calls, never by HTTP or a concurrent setter.
	f.server.summaryProofClock = func() time.Time { return f.envelope.Metadata.CapturedAt.Add(-time.Hour) }
	before, _, err := f.control.ArchiveState("p")
	if err != nil || before.Pending == nil {
		t.Fatal(err)
	}
	pending := f.control.Budget().Snapshot().Pending
	progress, err := f.intake.Progress()
	if err != nil {
		t.Fatal(err)
	}
	writes := f.source.derivedWrites
	err = f.server.RecoverArchive()
	after, _, stateErr := f.control.ArchiveState("p")
	afterProgress, progressErr := f.intake.Progress()
	if !errors.Is(err, summary.ErrVerifierClock) || errors.Is(err, summary.ErrInvalidStored) || stateErr != nil || progressErr != nil || !reflect.DeepEqual(before, after) || !reflect.DeepEqual(pending, f.control.Budget().Snapshot().Pending) || !reflect.DeepEqual(progress, afterProgress) || f.source.derivedWrites != writes {
		t.Fatal("temporary clock cancelled/processed accepted body", err, stateErr, progressErr)
	}
	f.server.summaryProofClock = nil
	f.source.failDerived = false
	if err = f.server.RecoverArchive(); err != nil {
		t.Fatal("corrected clock did not recover", err)
	}
	actual, found, err := f.source.LookupEnvelope(f.envelope.Record)
	want, _ := archive.EncodeEnvelope(f.envelope)
	got, _ := archive.EncodeEnvelope(actual)
	if err != nil || !found || string(want) != string(got) {
		t.Fatal("clock recovery regenerated accepted body/time/ordinal", found, err)
	}
	state, _, err := f.control.ArchiveState("p")
	if err != nil || state.Pending != nil || state.CommittedOrdinal != 2 || len(f.control.Budget().Snapshot().Pending) != 0 {
		t.Fatal("corrected recovery retained ambiguity", err)
	}
}
func TestSummaryRegressedProofClockServingIsTemporaryGenericFailure(t *testing.T) {
	f := newSummaryClockFixture(t, false)
	if err := f.control.IssueGrant(f.op, registry.Grant{PrincipalID: "clock-reader", Kind: registry.Agent, Projects: map[string]bool{"p": true}, Ops: map[registry.Op]bool{registry.OpArchiveQuery: true}, Epoch: 1, Secret: "synthetic-clock-reader"}); err != nil {
		t.Fatal(err)
	}
	f.server.summaryProofClock = func() time.Time { return f.envelope.Metadata.CapturedAt.Add(-time.Hour) }
	identity := url.Values{"project": {"p"}, "source_instance": {"i"}, "session_id": {"s"}, "message_id": {f.envelope.Record.MessageID}}
	paths := []string{"/v1/archive/message?" + identity.Encode(), "/v1/archive/context?" + identity.Encode(), "/v1/archive/query?project=p"}
	handler := f.server.Handler()
	for _, path := range paths {
		req := httptest.NewRequest(http.MethodGet, path, nil)
		req.Header.Set("X-Principal-Id", "clock-reader")
		req.Header.Set("X-Grant-Epoch", "1")
		req.Header.Set("X-Secret", "synthetic-clock-reader")
		out := httptest.NewRecorder()
		handler.ServeHTTP(out, req)
		var body map[string]any
		err := json.Unmarshal(out.Body.Bytes(), &body)
		if out.Code != 503 || err != nil || !reflect.DeepEqual(body, map[string]any{"error": "archive read failed"}) || strings.Contains(out.Body.String(), "synthetic clock fixture source") {
			t.Fatal("clock uncertainty served or permanently hid derived data", path, out.Code, out.Body.String(), err)
		}
	}
	f.server.summaryProofClock = nil
	req := httptest.NewRequest(http.MethodGet, paths[0], nil)
	req.Header.Set("X-Principal-Id", "clock-reader")
	req.Header.Set("X-Grant-Epoch", "1")
	req.Header.Set("X-Secret", "synthetic-clock-reader")
	out := httptest.NewRecorder()
	handler.ServeHTTP(out, req)
	if out.Code != 200 {
		t.Fatal("clock correction not retryable", out.Code, out.Body.String())
	}
}
