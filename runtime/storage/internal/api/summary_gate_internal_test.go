package api

import (
	"aifactory.local/storage/internal/archive"
	"aifactory.local/storage/internal/budget"
	"aifactory.local/storage/internal/config"
	"aifactory.local/storage/internal/control"
	"aifactory.local/storage/internal/ingest"
	"aifactory.local/storage/internal/registry"
	"aifactory.local/storage/internal/summary"
	"context"
	"encoding/json"
	"errors"
	"path/filepath"
	"reflect"
	"strings"
	"testing"
	"time"
)

func TestSummaryPublishCacheBindsExactRecordAndMetadata(t *testing.T) {
	for _, kind := range []string{"record", "metadata"} {
		t.Run(kind, func(t *testing.T) {
			root := t.TempDir()
			d, err := control.Initialize(filepath.Join(root, "control"))
			if err != nil {
				t.Fatal(err)
			}
			defer d.Close()
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
			store := archive.NewMemStore()
			i, err := ingest.Open(filepath.Join(root, "ingest"), config.NewAccountant(config.Default()), store)
			if err != nil {
				t.Fatal(err)
			}
			defer i.Close()
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
			r := archive.Record{Project: "p", Provider: "synthetic", SourceInstance: "i", SessionID: "s", MessageID: "original", Role: "user", Type: archive.TypeMessage, Text: "synthetic cache proof", ConsentEpoch: 1}
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
			derived, err := summary.SealExtract(doc, summary.Authority{ConsentEpoch: epoch, Activation: baseline}, in.Messages, now)
			if err != nil {
				t.Fatal(err)
			}
			var envelope archive.Envelope
			if err = d.WithArchiveTransaction(op, "p", func(tx *control.ArchiveTransaction) error {
				var e error
				envelope, e = tx.ReserveSummary(derived, epoch)
				if e != nil {
					return e
				}
				_, e = i.CommitEnvelope(tx, envelope)
				return e
			}); err != nil {
				t.Fatal(err)
			}
			s := &Server{ing: i, ctl: d}
			if err = d.WithArchiveTransaction(op, "p", func(tx *control.ArchiveTransaction) error {
				gate := s.publishEnvelopeGate(tx)
				if allowed, e := gate(envelope); e != nil || !allowed {
					t.Fatal("valid initial proof", allowed, e)
				}
				changed := envelope
				if kind == "record" {
					changed.Record.Text = "{}"
				} else {
					at := doc.GeneratedAt.Add(-time.Nanosecond)
					changed.Metadata.CapturedAt = &at
				}
				if allowed, e := gate(changed); e != nil || allowed {
					t.Fatal("cache reused proof for changed envelope", kind, allowed, e)
				}
				if allowed, e := gate(envelope); e != nil || !allowed {
					t.Fatal("valid proof not retryable after rejected change", allowed, e)
				}
				return nil
			}); err != nil {
				t.Fatal(err)
			}
		})
	}
}
func TestSummaryCursorRefusesEncodedOverheadBeyondTransportBound(t *testing.T) {
	s := &Server{opSec: "synthetic-only"}
	c := pageCursor{Project: "p"}
	raw, err := json.Marshal(c)
	if err != nil {
		t.Fatal(err)
	}
	c.Provider = strings.Repeat("x", maxCursorPlaintext-len(raw))
	raw, err = json.Marshal(c)
	if err != nil || len(raw) != maxCursorPlaintext {
		t.Fatal("boundary fixture", len(raw), err)
	}
	if token, err := s.encodeCursor(c); err == nil || token != "" {
		t.Fatal("emitted cursor exceeds its own accepted transport bound", len(token), err)
	}
}

type contextDiscoveryProbe struct {
	*archive.MemStore
	calls        int
	query        archive.SummaryQuery
	after        *archive.SessionKey
	cancel       context.CancelFunc
	backendError error
}

func (s *contextDiscoveryProbe) NextSummarySession(q archive.SummaryQuery, a *archive.SessionKey) (archive.SessionKey, bool, error) {
	s.calls++
	s.query = q
	s.after = a
	if s.cancel != nil {
		s.cancel()
	}
	return archive.SessionKey{}, false, s.backendError
}
func TestSummaryDiscoveryContextBridgePreservesQueryAndStopsCancellation(t *testing.T) {
	q := archive.SummaryQuery{Project: "p", Provider: "v", Generation: "g", ActivationOrdinal: 1, Through: 7, RevokedThrough: 1, CaptureEpoch: 3}
	after := &archive.SessionKey{SourceInstance: "i", SessionID: "s"}
	for _, kind := range []string{"cancelled-before", "cancelled-exhaustion", "backend-error", "exhausted"} {
		t.Run(kind, func(t *testing.T) {
			source := &contextDiscoveryProbe{MemStore: archive.NewMemStore()}
			ctx, cancel := context.WithCancel(context.Background())
			defer cancel()
			wantCalls := 1
			want := error(nil)
			switch kind {
			case "cancelled-before":
				cancel()
				wantCalls = 0
				want = context.Canceled
			case "cancelled-exhaustion":
				source.cancel = cancel
				want = context.Canceled
			case "backend-error":
				source.backendError = errors.New("synthetic discovery read failed")
				want = source.backendError
			}
			_, found, err := nextSummarySessionContext(ctx, source, q, after)
			if !errors.Is(err, want) || found || source.calls != wantCalls {
				t.Fatal("legacy read cancellation/error contract", kind, found, err, source.calls)
			}
			if wantCalls > 0 && (!reflect.DeepEqual(source.query, q) || !reflect.DeepEqual(source.after, after)) {
				t.Fatal("query/cursor changed")
			}
		})
	}
}
