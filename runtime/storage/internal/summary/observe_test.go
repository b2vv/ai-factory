package summary

import (
	"aifactory.local/storage/internal/archive"
	"encoding/json"
	"errors"
	"fmt"
	"strings"
	"testing"
	"time"
)

func TestPrepareSessionUsesSourceFrontierNotSummaryOrdinal(t *testing.T) {
	head, originals, _ := storedFixture(t)
	store := archive.NewMemStore()
	if err := store.PutEnvelope(originals[0]); err != nil {
		t.Fatal(err)
	}
	// Original accepted after the first observation, but before its derived head.
	late := originals[0]
	late.Record.MessageID = "late"
	late.Record.ConsentEpoch = 3
	late.Metadata.Ordinal = 2
	at := head.Metadata.CapturedAt.Add(time.Minute)
	late.Metadata.CapturedAt = &at
	head.Metadata.Ordinal = 3
	accepted := at.Add(time.Minute)
	head.Metadata.CapturedAt = &accepted
	for _, e := range []archive.Envelope{late, head} {
		if err := store.PutEnvelope(e); err != nil {
			t.Fatal(err)
		}
	}
	var body StoredExtract
	body, err := DecodeStored(head)
	if err != nil {
		t.Fatal(err)
	}
	q := archive.SummaryQuery{Project: head.Record.Project, Provider: head.Record.Provider, Generation: head.Metadata.Generation, Through: 3, RevokedThrough: 2, CaptureEpoch: 3}
	key := archive.SessionKey{SourceInstance: head.Record.SourceInstance, SessionID: head.Record.SessionID}
	prepared, err := PrepareSession(store, q, key, Authority{ConsentEpoch: 7, Activation: body.Activation}, at.Add(15*time.Minute), DefaultConfig(), DefaultExtractOptions())
	if err != nil || !prepared.Decision.Ready {
		t.Fatal("late source stalled behind head", err, prepared.Decision)
	}
	if len(prepared.Decision.Selected) != 1 || prepared.Decision.Selected[0].Record.MessageID != "late" || prepared.Document.Manifest.Progress == nil || prepared.Document.Manifest.Progress.AfterOrdinal != 1 {
		t.Fatal("late source skipped or historical source repeated", prepared.Decision)
	}
	if prepared.Head == nil || prepared.Head.Metadata.Ordinal != 3 {
		t.Fatal("publish cannot revalidate prior head")
	}
}

type observerSource struct {
	archive.SummarySource
	head    archive.Envelope
	lookups int
}

func (s *observerSource) SummaryHead(archive.SummaryQuery, archive.SessionKey) (archive.Envelope, bool, error) {
	return s.head, true, nil
}
func (s *observerSource) LookupEnvelope(r archive.Record) (archive.Envelope, bool, error) {
	s.lookups++
	return s.SummarySource.LookupEnvelope(r)
}

func TestPrepareSessionBindsHeadScopeBeforeCoveredSourceLookup(t *testing.T) {
	for _, field := range []string{"provider", "source", "session"} {
		t.Run(field, func(t *testing.T) {
			head, _, now := storedFixture(t)
			body, err := DecodeStored(head)
			if err != nil {
				t.Fatal(err)
			}
			q := archive.SummaryQuery{Project: head.Record.Project, Provider: head.Record.Provider, Generation: head.Metadata.Generation, Through: head.Metadata.Ordinal, CaptureEpoch: 1}
			key := archive.SessionKey{SourceInstance: head.Record.SourceInstance, SessionID: head.Record.SessionID}
			switch field {
			case "provider":
				body.Document.Manifest.Scope.Provider = "foreign"
				head.Record.Provider = "foreign"
				body.Document.Manifest.Sources[0].Provider = "foreign"
			case "source":
				body.Document.Manifest.Scope.SourceInstance = "foreign"
				head.Record.SourceInstance = "foreign"
				body.Document.Manifest.Sources[0].Identity.SourceInstance = "foreign"
			case "session":
				body.Document.Manifest.Scope.SessionID = "foreign"
				head.Record.SessionID = "foreign"
				body.Document.Manifest.Sources[0].Identity.SessionID = "foreign"
			}
			body.Document.JobID = jobIdentity(body.Document.Manifest)
			body.Document.EvidenceHash = digest(body.Document.Manifest)
			raw, err := json.Marshal(body)
			if err != nil {
				t.Fatal(err)
			}
			head.Record.Text = string(raw)
			head.Record.MessageID = MessagePrefix + body.Document.JobID
			if _, err := DecodeStored(head); err != nil {
				t.Fatal("fixture invalid before scope guard", err)
			}
			source := &observerSource{SummarySource: archive.NewMemStore(), head: head}
			_, err = PrepareSession(source, q, key, Authority{ConsentEpoch: 7, Activation: body.Activation}, now, DefaultConfig(), DefaultExtractOptions())
			if err == nil || source.lookups != 0 {
				t.Fatal("unbound head permitted covered-source lookup", source.lookups, err)
			}
		})
	}
}

func TestPrepareSessionBoundsCrossingPageWithoutFalseGlobalCoverage(t *testing.T) {
	store := archive.NewMemStore()
	in := exampleInput()
	at := *in.Messages[0].Metadata.CapturedAt
	for i := int64(1); i <= 105; i++ {
		original := in.Messages[0]
		original.Record.MessageID = fmt.Sprint(i)
		original.Record.Text = strings.Repeat("x", 512)
		original.Metadata.Ordinal = i
		if err := store.PutEnvelope(original); err != nil {
			t.Fatal(err)
		}
	}
	q := archive.SummaryQuery{Project: in.Scope.Project, Provider: in.Scope.Provider, Generation: in.Generation, Through: 105, CaptureEpoch: 1}
	c := DefaultConfig()
	c.MaxInputBytes = 4096
	c.MaxObservationBytes = 4096
	got, err := PrepareSession(store, q, archive.SessionKey{SourceInstance: in.Scope.SourceInstance, SessionID: in.Scope.SessionID}, Authority{ConsentEpoch: 1, Activation: *in.Activation}, at.Add(time.Minute), c, DefaultExtractOptions())
	if err != nil || !got.Decision.Ready || got.Decision.Reason != "size" {
		t.Fatal("crossing page stalled", got.Decision, err)
	}
	if got.Document.Manifest.ObservedCutoff != 100 || len(got.Decision.Selected) == 0 || len(got.Decision.Selected) >= 100 || got.Document.Manifest.PendingOriginals != 100-len(got.Decision.Selected) {
		t.Fatal("false observed cutoff or skipped prefix", got.Document.Manifest)
	}
	for i, e := range got.Decision.Selected {
		if e.Metadata.Ordinal != int64(i+1) {
			t.Fatal("non-prefix selection", e.Metadata.Ordinal)
		}
	}
}

func TestPrepareSessionMissingHeadSourcesBlocksInsteadOfRepeatingHistory(t *testing.T) {
	head, _, now := storedFixture(t)
	body, err := DecodeStored(head)
	if err != nil {
		t.Fatal(err)
	}
	source := &observerSource{SummarySource: archive.NewMemStore(), head: head}
	q := archive.SummaryQuery{Project: head.Record.Project, Provider: head.Record.Provider, Generation: head.Metadata.Generation, Through: head.Metadata.Ordinal, CaptureEpoch: 1}
	got, err := PrepareSession(source, q, archive.SessionKey{SourceInstance: head.Record.SourceInstance, SessionID: head.Record.SessionID}, Authority{ConsentEpoch: 7, Activation: body.Activation}, now, DefaultConfig(), DefaultExtractOptions())
	if !errors.Is(err, ErrInvalidStored) || got.Decision.Ready || source.lookups != 1 {
		t.Fatal("missing source reset factual progress", got, source.lookups, err)
	}
}

type adverseObservationSource struct {
	archive.SummarySource
	head                  *archive.Envelope
	missingSchema         bool
	heads, lookups, scans int
	page                  func(int) (archive.EnvelopeWindow, error)
}

func (s *adverseObservationSource) SummarySchemaReady() (bool, error) {
	if s.missingSchema {
		return false, nil
	}
	return s.SummarySource.SummarySchemaReady()
}
func (s *adverseObservationSource) SummaryHead(archive.SummaryQuery, archive.SessionKey) (archive.Envelope, bool, error) {
	s.heads++
	if s.head != nil {
		return *s.head, true, nil
	}
	return archive.Envelope{}, false, nil
}
func (s *adverseObservationSource) LookupEnvelope(r archive.Record) (archive.Envelope, bool, error) {
	s.lookups++
	return s.SummarySource.LookupEnvelope(r)
}
func (s *adverseObservationSource) ScanSummaryOriginals(q archive.SummaryQuery, k archive.SessionKey, a int64) (archive.EnvelopeWindow, error) {
	s.scans++
	if s.page != nil {
		return s.page(s.scans)
	}
	return s.SummarySource.ScanSummaryOriginals(q, k, a)
}
func TestPrepareSessionRejectsInvalidBoundaryBeforeDependentIO(t *testing.T) {
	for _, kind := range []string{"authority-epoch", "activation-ordinal", "missing-schema", "head-cutoff", "head-epoch", "head-activation"} {
		t.Run(kind, func(t *testing.T) {
			head, originals, now := storedFixture(t)
			body, err := DecodeStored(head)
			if err != nil {
				t.Fatal(err)
			}
			mem := archive.NewMemStore()
			for _, e := range originals {
				if err = mem.PutEnvelope(e); err != nil {
					t.Fatal(err)
				}
			}
			source := &adverseObservationSource{SummarySource: mem}
			q := archive.SummaryQuery{Project: head.Record.Project, Provider: head.Record.Provider, Generation: head.Metadata.Generation, Through: head.Metadata.Ordinal, CaptureEpoch: 1}
			a := Authority{ConsentEpoch: 7, Activation: body.Activation}
			wantHeads := 0
			switch kind {
			case "authority-epoch":
				a.ConsentEpoch = 0
			case "activation-ordinal":
				q.ActivationOrdinal++
			case "missing-schema":
				source.missingSchema = true
			case "head-cutoff":
				source.head = &head
				q.Through = head.Metadata.Ordinal - 1
				wantHeads = 1
			case "head-epoch":
				source.head = &head
				a.ConsentEpoch++
				wantHeads = 1
			case "head-activation":
				source.head = &head
				a.Activation.At = a.Activation.At.Add(time.Nanosecond)
				wantHeads = 1
			}
			out, err := PrepareSession(source, q, archive.SessionKey{SourceInstance: head.Record.SourceInstance, SessionID: head.Record.SessionID}, a, now, DefaultConfig(), DefaultExtractOptions())
			if err == nil || out.Decision.Ready || source.heads != wantHeads || source.lookups != 0 || source.scans != 0 {
				t.Fatal("invalid observation started dependent IO", kind, err, source.heads, source.lookups, source.scans)
			}
		})
	}
}
func TestPrepareSessionRejectsNonprogressingAndOutOfCutoffPages(t *testing.T) {
	for _, kind := range []string{"empty-more", "duplicate-more", "beyond-cutoff-crossing"} {
		t.Run(kind, func(t *testing.T) {
			in := exampleInput()
			source := &adverseObservationSource{SummarySource: archive.NewMemStore()}
			record := in.Messages[0]
			record.Record.Text = strings.Repeat("x", 400)
			q := archive.SummaryQuery{Project: in.Scope.Project, Provider: in.Scope.Provider, Generation: in.Generation, Through: 1, CaptureEpoch: 1}
			source.page = func(call int) (archive.EnvelopeWindow, error) {
				if call > 2 {
					return archive.EnvelopeWindow{}, errors.New("synthetic unexpected additional source page")
				}
				switch kind {
				case "empty-more":
					return archive.EnvelopeWindow{More: true}, nil
				case "duplicate-more":
					return archive.EnvelopeWindow{Records: []archive.Envelope{record}, More: true}, nil
				default:
					page := archive.EnvelopeWindow{More: true}
					for i := int64(2); i <= 4; i++ {
						e := record
						e.Record.MessageID = fmt.Sprint(i)
						e.Metadata.Ordinal = i
						page.Records = append(page.Records, e)
					}
					return page, nil
				}
			}
			c := DefaultConfig()
			c.MaxInputBytes = 1024
			out, err := PrepareSession(source, q, archive.SessionKey{SourceInstance: in.Scope.SourceInstance, SessionID: in.Scope.SessionID}, Authority{ConsentEpoch: 1, Activation: *in.Activation}, in.Messages[0].Metadata.CapturedAt.Add(time.Hour), c, DefaultExtractOptions())
			wantScans := 1
			if kind == "duplicate-more" {
				wantScans = 2
			}
			if err == nil || out.Decision.Ready || source.scans != wantScans {
				t.Fatal("invalid raw page advanced observation", kind, err, source.scans)
			}
			if kind != "empty-more" && !errors.Is(err, ErrInvalidStored) {
				t.Fatal("invalid ordinal was not refused at source boundary", err)
			}
		})
	}
}
