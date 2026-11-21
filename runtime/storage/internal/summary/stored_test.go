package summary

import (
	"aifactory.local/storage/internal/archive"
	"context"
	"encoding/json"
	"errors"
	"strconv"
	"strings"
	"testing"
	"time"
)

func TestStoredExtractBindsOriginalsAndSeparateConsent(t *testing.T) {
	in := exampleInput()
	in.GeneratorVersion = ""
	now := in.Messages[0].Metadata.CapturedAt.Add(15 * time.Minute)
	doc, d, e := GenerateExtract(DefaultConfig(), now, in, DefaultExtractOptions())
	if e != nil || !d.Ready {
		t.Fatal(e)
	}
	authority := Authority{ConsentEpoch: 7, Activation: *in.Activation}
	record, e := SealExtract(doc, authority, in.Messages, now)
	if e != nil {
		t.Fatal(e)
	}
	if record.Type != archive.TypeSummary || record.Role != "assistant" || record.ConsentEpoch != in.Messages[0].Record.ConsentEpoch || record.MessageID != "af-summary-v1/"+d.JobID || record.Project != in.Scope.Project || record.Provider != in.Scope.Provider {
		t.Fatal("invalid durable binding", record)
	}
	captured := now.Add(time.Nanosecond)
	envelope := archive.Envelope{Version: 2, Record: record, Metadata: archive.Metadata{Generation: in.Generation, Ordinal: in.Cutoff + 1, CapturedAt: &captured, DerivedKind: archive.DerivedSessionExtract}}
	got, e := VerifyStored(envelope, in.Messages, captured)
	if e != nil || got.ConsentEpoch != 7 || got.Document.JobID != d.JobID || got.Activation.Ordinal != in.Activation.Ordinal {
		t.Fatal("stored proof rejected", got, e)
	}
	if in.Messages[0].Record.Text != "A concrete source statement" {
		t.Fatal("source text mutated")
	}
}

func TestStoredExtractDoesNotInventBranchEvidence(t *testing.T) {
	in := exampleInput()
	in.GeneratorVersion = ""
	in.Scope.BranchKnown = true
	in.Scope.Branch = "main"
	now := in.Messages[0].Metadata.CapturedAt.Add(15 * time.Minute)
	doc, _, e := GenerateExtract(DefaultConfig(), now, in, DefaultExtractOptions())
	if e != nil {
		t.Fatal(e)
	}
	if _, e = SealExtract(doc, Authority{ConsentEpoch: 1, Activation: *in.Activation}, in.Messages, now); e == nil {
		t.Fatal("v2 source metadata cannot attest the supplied branch")
	}
}
func TestStoredDecodeAdmissionPrecedesEnvelopeSerialization(t *testing.T) {
	in := exampleInput()
	at := *in.Messages[0].Metadata.CapturedAt
	e := archive.Envelope{Version: 2, Record: archive.Record{Project: "p", Provider: "synthetic", SourceInstance: "i", SessionID: "s", MessageID: MessagePrefix + strings.Repeat("a", 64), Type: archive.TypeSummary, Role: "assistant", Text: strings.Repeat("x", 8<<20)}, Metadata: archive.Metadata{Generation: "g", Ordinal: 2, CapturedAt: &at, DerivedKind: archive.DerivedSessionExtract}}
	n := allocatedExtractBytes(func() {
		if _, err := DecodeStored(e); err == nil {
			t.Fatal("oversized body admitted")
		}
	})
	if n > 128<<10 {
		t.Fatalf("allocated %d bytes before rejecting oversized stored body", n)
	}
}

func storedFixture(t *testing.T) (archive.Envelope, []archive.Envelope, time.Time) {
	t.Helper()
	in := exampleInput()
	in.GeneratorVersion = ""
	now := in.Messages[0].Metadata.CapturedAt.Add(15 * time.Minute)
	doc, d, err := GenerateExtract(DefaultConfig(), now, in, DefaultExtractOptions())
	if err != nil || !d.Ready {
		t.Fatal("fixture generation", err)
	}
	record, err := SealExtract(doc, Authority{ConsentEpoch: 7, Activation: *in.Activation}, in.Messages, now)
	if err != nil {
		t.Fatal("fixture seal", err)
	}
	captured := now.Add(time.Nanosecond)
	return archive.Envelope{Version: 2, Record: record, Metadata: archive.Metadata{Generation: in.Generation, Ordinal: in.Cutoff + 1, CapturedAt: &captured, DerivedKind: archive.DerivedSessionExtract}}, in.Messages, captured
}

func TestStoredProofRejectsChangedSourcesAndFabricatedExcerpts(t *testing.T) {
	for _, kind := range []string{"source-text", "source-identity", "source-epoch", "source-time", "excerpt-text", "excerpt-offset", "excerpt-length", "excerpt-role", "source-reference", "unknown-field", "duplicate-field", "trailing-json", "noncanonical"} {
		t.Run(kind, func(t *testing.T) {
			envelope, sources, now := storedFixture(t)
			var body StoredExtract
			if err := json.Unmarshal([]byte(envelope.Record.Text), &body); err != nil {
				t.Fatal(err)
			}
			switch kind {
			case "source-text":
				sources[0].Record.Text = "altered original"
			case "source-identity":
				sources[0].Record.Project = "another-project"
			case "source-epoch":
				sources[0].Record.ConsentEpoch++
			case "source-time":
				at := sources[0].Metadata.CapturedAt.Add(time.Nanosecond)
				sources[0].Metadata.CapturedAt = &at
			case "excerpt-text":
				body.Document.Excerpts[0].Text = "invented assertion"
			case "excerpt-offset":
				body.Document.Excerpts[0].Start = 1
			case "excerpt-length":
				body.Document.Excerpts[0].SourceBytes++
			case "excerpt-role":
				body.Document.Excerpts[0].Role = "assistant"
			case "source-reference":
				body.Document.Manifest.Sources[0].Identity.Project = "another-project"
			}
			if strings.HasPrefix(kind, "excerpt-") || kind == "source-reference" {
				body.Document.JobID = jobIdentity(body.Document.Manifest)
				body.Document.EvidenceHash = digest(body.Document.Manifest)
				raw, err := json.Marshal(body)
				if err != nil {
					t.Fatal(err)
				}
				envelope.Record.Text = string(raw)
				envelope.Record.MessageID = MessagePrefix + body.Document.JobID
			}
			switch kind {
			case "unknown-field":
				envelope.Record.Text = strings.Replace(envelope.Record.Text, "{", "{\"unknown\":1,", 1)
			case "duplicate-field":
				envelope.Record.Text = strings.Replace(envelope.Record.Text, "{", "{\"format\":\"discarded\",", 1)
			case "trailing-json":
				envelope.Record.Text += "{}"
			case "noncanonical":
				envelope.Record.Text = " " + envelope.Record.Text
			}
			if _, err := VerifyStored(envelope, sources, now); err == nil {
				t.Fatal("accepted changed proof", kind)
			}
		})
	}
}

func TestStoredEnvelopeRequiresExplicitMarkerScopeAndCommittedOrder(t *testing.T) {
	for _, kind := range []string{"unmarked", "unknown-marker", "old-version", "project", "provider", "source", "session", "generation", "uncommitted-order", "capture-before-generation", "verify-before-capture", "unknown-capture", "role", "seq", "parent", "edited", "withdrawn", "record-epoch", "job-id"} {
		t.Run(kind, func(t *testing.T) {
			e, sources, now := storedFixture(t)
			switch kind {
			case "unmarked":
				e.Metadata.DerivedKind = ""
			case "unknown-marker":
				e.Metadata.DerivedKind = "future-version"
			case "old-version":
				e.Version = 1
			case "project":
				e.Record.Project = "another-project"
			case "provider":
				e.Record.Provider = "another-provider"
			case "source":
				e.Record.SourceInstance = "another-source"
			case "session":
				e.Record.SessionID = "another-session"
			case "generation":
				e.Metadata.Generation = "another-generation"
			case "uncommitted-order":
				e.Metadata.Ordinal = 1
			case "capture-before-generation":
				at := now.Add(-time.Second)
				e.Metadata.CapturedAt = &at
			case "verify-before-capture":
				now = now.Add(-time.Nanosecond)
			case "unknown-capture":
				e.Metadata.CapturedAt = nil
			case "role":
				e.Record.Role = "user"
			case "seq":
				e.Record.Seq = 1
			case "parent":
				e.Record.ParentID = "invented-parent"
			case "edited":
				e.Record.Edited = true
			case "withdrawn":
				e.Record.Withdrawn = true
			case "record-epoch":
				e.Record.ConsentEpoch = 2
			case "job-id":
				e.Record.MessageID = MessagePrefix + strings.Repeat("a", 64)

			}
			if _, err := VerifyStored(e, sources, now); err == nil {
				t.Fatal("invalid stored envelope admitted", kind)
			}
		})
	}
}

func TestSealRejectsOversizedProgressBeforeAllocation(t *testing.T) {
	e, _, _ := storedFixture(t)
	var body StoredExtract
	if err := json.Unmarshal([]byte(e.Record.Text), &body); err != nil {
		t.Fatal(err)
	}
	body.Document.Manifest.Progress = &Progress{AfterOrdinal: 1, PreviousJobID: strings.Repeat("x", 8<<20)}
	allocated := allocatedExtractBytes(func() {
		if _, err := SealExtract(body.Document, Authority{ConsentEpoch: 7, Activation: body.Activation}, nil, body.Document.GeneratedAt); err == nil {
			t.Fatal("oversized progress admitted")
		}
	})
	if allocated > 128<<10 {
		t.Fatalf("allocated %d bytes for oversized progress", allocated)
	}
}

type lookupFailureStore struct {
	archive.MetadataStore
	failure error
	missing bool
}

func (s lookupFailureStore) LookupEnvelope(r archive.Record) (archive.Envelope, bool, error) {
	if s.failure != nil {
		return archive.Envelope{}, false, s.failure
	}
	if s.missing {
		return archive.Envelope{}, false, nil
	}
	return s.MetadataStore.LookupEnvelope(r)
}

func TestLoadStoredSeparatesMissingSourcesFromTransientReadFailure(t *testing.T) {
	e, originals, now := storedFixture(t)
	store := archive.NewMemStore()
	for _, source := range originals {
		if err := store.PutEnvelope(source); err != nil {
			t.Fatal(err)
		}
	}
	unavailable := errors.New("synthetic backend read unavailable")
	for _, row := range []struct {
		name   string
		source archive.MetadataStore
		want   error
	}{
		{"current", store, nil},
		{"missing", lookupFailureStore{MetadataStore: store, missing: true}, ErrInvalidStored},
		{"transient", lookupFailureStore{MetadataStore: store, failure: unavailable}, unavailable},
	} {
		t.Run(row.name, func(t *testing.T) {
			proof, sources, err := LoadStored(e, row.source, now)
			if !errors.Is(err, row.want) {
				t.Fatal("read failure changed meaning", err, row.want)
			}
			if row.want == nil && (proof.ConsentEpoch != 7 || len(sources) != 1 || sources[0].Record.MessageID != originals[0].Record.MessageID) {
				t.Fatal("source proof not loaded", proof, len(sources))
			}
			if row.want != nil && len(sources) != 0 {
				t.Fatal("partial source proof escaped")
			}
		})
	}
}

func TestSealRejectsOversizedJobBeforeIdentityAllocation(t *testing.T) {
	e, _, _ := storedFixture(t)
	var body StoredExtract
	if err := json.Unmarshal([]byte(e.Record.Text), &body); err != nil {
		t.Fatal(err)
	}
	body.Document.JobID = strings.Repeat("x", 8<<20)
	allocated := allocatedExtractBytes(func() {
		if _, err := SealExtract(body.Document, Authority{ConsentEpoch: 7, Activation: body.Activation}, nil, body.Document.GeneratedAt); err == nil {
			t.Fatal("oversized job admitted")
		}
	})
	if allocated > 128<<10 {
		t.Fatalf("allocated %d bytes before rejecting oversized job", allocated)
	}
}

type proofContextLookup struct {
	*archive.MemStore
	calls  int
	cancel context.CancelFunc
}

func (s *proofContextLookup) LookupEnvelope(r archive.Record) (archive.Envelope, bool, error) {
	s.calls++
	e, found, err := s.MemStore.LookupEnvelope(r)
	if s.cancel != nil {
		s.cancel()
	}
	return e, found, err
}
func TestLoadStoredContextStopsFurtherIOAndReturnsNoPartialProof(t *testing.T) {
	in := exampleInput()
	second := in.Messages[0]
	second.Record.MessageID = "second"
	second.Record.Role = "assistant"
	second.Metadata.Ordinal = 2
	in.Messages = append(in.Messages, second)
	in.Cutoff = 2
	in.GeneratorVersion = ""
	now := in.Messages[0].Metadata.CapturedAt.Add(15 * time.Minute)
	doc, decision, err := GenerateExtract(DefaultConfig(), now, in, DefaultExtractOptions())
	if err != nil || !decision.Ready {
		t.Fatal(err)
	}
	record, err := SealExtract(doc, Authority{ConsentEpoch: 7, Activation: *in.Activation}, in.Messages, now)
	if err != nil {
		t.Fatal(err)
	}
	e := archive.Envelope{Version: 2, Record: record, Metadata: archive.Metadata{Generation: in.Generation, Ordinal: 3, CapturedAt: &now, DerivedKind: archive.DerivedSessionExtract}}
	for _, kind := range []string{"nil", "cancelled-before", "expired", "cancelled-after-first"} {
		t.Run(kind, func(t *testing.T) {
			source := &proofContextLookup{MemStore: archive.NewMemStore()}
			for _, original := range in.Messages {
				if err := source.PutEnvelope(original); err != nil {
					t.Fatal(err)
				}
			}
			ctx, cancel := context.WithCancel(context.Background())
			defer cancel()
			wantCalls := 0
			want := error(context.Canceled)
			switch kind {
			case "nil":
				ctx = nil
				want = nil
			case "cancelled-before":
				cancel()
			case "expired":
				expired, stop := context.WithDeadline(context.Background(), time.Now().Add(-time.Second))
				defer stop()
				ctx = expired
				want = context.DeadlineExceeded
			case "cancelled-after-first":
				source.cancel = cancel
				wantCalls = 1
			}
			proof, originals, err := LoadStoredContext(ctx, e, source, now)
			if err == nil || (want != nil && !errors.Is(err, want)) || proof.Format != "" || len(originals) != 0 || source.calls != wantCalls {
				t.Fatal("cancelled source IO returned partial proof or continued", kind, err, source.calls)
			}
		})
	}
}

func TestStoredJSONShapeAdmissionBounds(t *testing.T) {
	array := func(n int) string { return "[" + strings.Repeat("0,", n-1) + "0]" }
	object := func(n int) string {
		var b strings.Builder
		b.Grow(n * 12)
		b.WriteByte('{')
		for i := 0; i < n; i++ {
			if i > 0 {
				b.WriteByte(',')
			}
			b.WriteString(strconv.Quote(strconv.Itoa(i)))
			b.WriteString(":0")
		}
		b.WriteByte('}')
		return b.String()
	}
	for _, tc := range []struct {
		name, raw string
		allowed   bool
	}{
		{"array-at-bound", array(4096), true}, {"array-over-bound", array(4097), false},
		{"scalar", "0", true},
		{"object-array-at-bound", "[" + strings.Repeat("{},", 4095) + "{}]", true},
		{"object-array-over-bound", "[" + strings.Repeat("{},", 4096) + "{}]", false},
		{"depth-at-bound", strings.Repeat("[", 16) + "0" + strings.Repeat("]", 16), true},
		{"depth-over-bound", strings.Repeat("[", 17) + "0" + strings.Repeat("]", 17), false},
		{"tokens-below-bound", object(131070), true}, {"tokens-over-bound", object(131072), false},
		{"unterminated-array", "[", false}, {"malformed-token", "{x}", false},
	} {
		t.Run(tc.name, func(t *testing.T) {
			if err := boundedJSON(tc.raw); (err == nil) != tc.allowed {
				t.Fatal("JSON shape/work admission", tc.name, err)
			}
		})
	}
}
func TestStoredEmptyObjectArraysRefuseBeforeTypedAllocation(t *testing.T) {
	for _, field := range []string{"sources", "excerpts"} {
		t.Run(field, func(t *testing.T) {
			e, _, _ := storedFixture(t)
			items := strings.Repeat("{},", 19999) + "{}"
			if field == "sources" {
				e.Record.Text = `{"document":{"coverage":{"sources":[` + items + `]}}}`
			} else {
				e.Record.Text = `{"document":{"excerpts":[` + items + `]}}`
			}
			allocated := allocatedExtractBytes(func() {
				if _, err := DecodeStored(e); err == nil {
					t.Fatal("oversized typed array accepted")
				}
			})
			if allocated > 2<<20 {
				t.Fatalf("typed array allocated %d bytes before shape refusal", allocated)
			}
		})
	}
}
func TestStoredTypedDocumentAdmissionPrecedesSerialization(t *testing.T) {
	for _, kind := range []string{"excerpt-count", "source-count", "huge-excerpt"} {
		t.Run(kind, func(t *testing.T) {
			e, originals, now := storedFixture(t)
			body, err := DecodeStored(e)
			if err != nil {
				t.Fatal(err)
			}
			doc := body.Document
			switch kind {
			case "excerpt-count":
				doc.Excerpts = make([]Excerpt, 4097)
			case "source-count":
				doc.Manifest.Sources = make([]SourceRef, 4097)
			case "huge-excerpt":
				doc.Excerpts[0].Text = strings.Repeat("x", 8<<20)
			}
			allocated := allocatedExtractBytes(func() {
				if _, err := SealExtract(doc, Authority{ConsentEpoch: body.ConsentEpoch, Activation: body.Activation}, originals, now); err == nil {
					t.Fatal("oversized typed document accepted")
				}
			})
			if allocated > 128<<10 {
				t.Fatalf("typed document allocated %d bytes before admission", allocated)
			}
		})
	}
}
func TestStoredEncodedExcerptCrossingRefusesBeforeWholeDocumentCopy(t *testing.T) {
	e, originals, now := storedFixture(t)
	body, err := DecodeStored(e)
	if err != nil {
		t.Fatal(err)
	}
	doc := body.Document
	doc.Excerpts[0].Text = strings.Repeat("\x00", 200000)
	allocated := allocatedExtractBytes(func() {
		if _, err := SealExtract(doc, Authority{ConsentEpoch: body.ConsentEpoch, Activation: body.Activation}, originals, now); err == nil {
			t.Fatal("encoded excerpt crossed complete budget")
		}
	})
	if allocated > 2<<20 {
		t.Fatalf("copied whole oversized document after excerpt crossed budget: %d bytes", allocated)
	}
}
func TestStoredMarshalDocumentChecksFinalNilArrayExpansion(t *testing.T) {
	e, _, _ := storedFixture(t)
	body, err := DecodeStored(e)
	if err != nil {
		t.Fatal(err)
	}
	doc := body.Document
	doc.Excerpts = nil
	doc.Notice = ""
	header := doc
	header.Excerpts = []Excerpt{}
	raw, err := json.Marshal(header)
	if err != nil {
		t.Fatal(err)
	}
	doc.Notice = strings.Repeat("x", (1<<20)-1-len(raw))
	header = doc
	header.Excerpts = []Excerpt{}
	raw, err = json.Marshal(header)
	if err != nil || len(raw) != (1<<20)-1 {
		t.Fatal("final budget fixture", len(raw), err)
	}
	if raw, err := marshalDocument(doc); err == nil || len(raw) != 0 {
		t.Fatal("nil-array encoded expansion bypassed final admission", len(raw), err)
	}
}
func TestStoredOuterStringsRejectBeforeEnvelopeSerialization(t *testing.T) {
	for _, field := range []string{"project", "provider", "source", "session", "message", "parent", "role"} {
		t.Run(field, func(t *testing.T) {
			e, _, _ := storedFixture(t)
			huge := strings.Repeat("x", 8<<20)
			switch field {
			case "project":
				e.Record.Project = huge
			case "provider":
				e.Record.Provider = huge
			case "source":
				e.Record.SourceInstance = huge
			case "session":
				e.Record.SessionID = huge
			case "message":
				e.Record.MessageID = huge
			case "parent":
				e.Record.ParentID = huge
			case "role":
				e.Record.Role = huge
			}
			allocated := allocatedExtractBytes(func() {
				if _, err := DecodeStored(e); err == nil {
					t.Fatal("oversized outer identity accepted")
				}
			})
			if allocated > 128<<10 {
				t.Fatalf("outer %s serialized before refusal: %d bytes", field, allocated)
			}
		})
	}
}
func TestSealAuthorityStringsRejectBeforeWrapperSerialization(t *testing.T) {
	for _, field := range []string{"project", "generation"} {
		t.Run(field, func(t *testing.T) {
			e, originals, now := storedFixture(t)
			body, err := DecodeStored(e)
			if err != nil {
				t.Fatal(err)
			}
			a := Authority{ConsentEpoch: body.ConsentEpoch, Activation: body.Activation}
			huge := strings.Repeat("x", 8<<20)
			if field == "project" {
				a.Activation.Project = huge
			} else {
				a.Activation.Generation = huge
			}
			allocated := allocatedExtractBytes(func() {
				if _, err := SealExtract(body.Document, a, originals, now); err == nil {
					t.Fatal("oversized authority accepted")
				}
			})
			if allocated > 128<<10 {
				t.Fatalf("authority %s serialized before refusal: %d bytes", field, allocated)
			}
		})
	}
}
func TestStoredTwoExcerptCommaBudgetPrecedesWholeDocumentCopy(t *testing.T) {
	e, _, _ := storedPairFixture(t)
	body, err := DecodeStored(e)
	if err != nil {
		t.Fatal(err)
	}
	doc := body.Document
	raw, err := json.Marshal(doc)
	if err != nil {
		t.Fatal(err)
	}
	doc.Excerpts[1].Text = strings.Repeat("x", (1<<20)+1-len(raw))
	raw, err = json.Marshal(doc)
	if err != nil || len(raw) != (1<<20)+1 {
		t.Fatal("two-excerpt boundary fixture", len(raw), err)
	}
	allocated := allocatedExtractBytes(func() {
		if raw, err := marshalDocument(doc); err == nil || len(raw) != 0 {
			t.Fatal("two-excerpt encoded bound bypassed", len(raw), err)
		}
	})
	if allocated > 2<<20 {
		t.Fatalf("comma crossing serialized whole oversized document: %d bytes", allocated)
	}
}

func reencodeStoredFixture(t *testing.T, e archive.Envelope, body StoredExtract) archive.Envelope {
	t.Helper()
	body.Document.JobID = jobIdentity(body.Document.Manifest)
	body.Document.EvidenceHash = digest(body.Document.Manifest)
	raw, err := json.Marshal(body)
	if err != nil {
		t.Fatal(err)
	}
	e.Record.Text = string(raw)
	e.Record.MessageID = MessagePrefix + body.Document.JobID
	return e
}
func TestStoredWireLabelsAndCoverageCannotMakeFalseClaims(t *testing.T) {
	for _, kind := range []string{"stored-format", "summary-epoch", "activation-ordinal", "document-format", "kind", "extractor", "notice", "coverage-format", "capture-completeness", "pending-negative", "pending-overflow", "empty-sources", "unequal-excerpts", "generator"} {
		t.Run(kind, func(t *testing.T) {
			e, _, _ := storedFixture(t)
			body, err := DecodeStored(e)
			if err != nil {
				t.Fatal(err)
			}
			switch kind {
			case "stored-format":
				body.Format = "other"
			case "summary-epoch":
				body.ConsentEpoch = 0
			case "activation-ordinal":
				body.Document.Manifest.ActivationOrdinal++
			case "document-format":
				body.Document.Format = "other"
			case "kind":
				body.Document.Kind = "semantic"
			case "extractor":
				body.Document.Extractor = "remote-model"
			case "notice":
				body.Document.Notice = "complete semantic summary"
			case "coverage-format":
				body.Document.Manifest.Format = "other"
			case "capture-completeness":
				body.Document.Manifest.CaptureCompleteness = "complete"
			case "pending-negative":
				body.Document.Manifest.PendingOriginals = -1
			case "pending-overflow":
				body.Document.Manifest.PendingOriginals = body.Document.Manifest.Config.MaxObservationBytes/2 + 1
			case "empty-sources":
				body.Document.Manifest.Sources = []SourceRef{}
				body.Document.Excerpts = []Excerpt{}
				e.Record.ConsentEpoch = 0
			case "unequal-excerpts":
				body.Document.Excerpts = []Excerpt{}
			case "generator":
				body.Document.Manifest.GeneratorVersion = "different-semantic-generator"
			}
			e = reencodeStoredFixture(t, e, body)
			if _, err := archive.EncodeEnvelope(e); err != nil {
				t.Fatal("outer envelope masks wire admission", kind, err)
			}
			if _, err := DecodeStored(e); !errors.Is(err, ErrInvalidStored) {
				t.Fatal("false wire claim accepted", kind, err)
			}
		})
	}
}
func TestStoredReferenceScopeRejectsBeforeAnyLookup(t *testing.T) {
	for _, kind := range []string{"project", "provider", "source", "session", "message-size"} {
		t.Run(kind, func(t *testing.T) {
			e, originals, now := storedFixture(t)
			body, err := DecodeStored(e)
			if err != nil {
				t.Fatal(err)
			}
			ref := &body.Document.Manifest.Sources[0]
			switch kind {
			case "project":
				ref.Identity.Project = "foreign"
			case "provider":
				ref.Provider = "foreign"
			case "source":
				ref.Identity.SourceInstance = "foreign"
			case "session":
				ref.Identity.SessionID = "foreign"
			case "message-size":
				ref.Identity.MessageID = strings.Repeat("m", 4097)
			}
			e = reencodeStoredFixture(t, e, body)
			source := &proofContextLookup{MemStore: archive.NewMemStore()}
			for _, r := range originals {
				if err := source.PutEnvelope(r); err != nil {
					t.Fatal(err)
				}
			}
			if _, _, err := LoadStored(e, source, now); !errors.Is(err, ErrInvalidStored) || source.calls != 0 {
				t.Fatal("unbound source reference reached resolver", kind, err, source.calls)
			}
		})
	}
}
func storedPairFixture(t *testing.T) (archive.Envelope, []archive.Envelope, time.Time) {
	t.Helper()
	in := exampleInput()
	in.GeneratorVersion = ""
	in.Messages[0].Record.Text = "🙂éx"
	in.Messages[0].Record.ConsentEpoch = 3
	second := in.Messages[0]
	second.Record.MessageID = "second"
	second.Record.Role = "assistant"
	second.Record.Text = ""
	second.Record.ConsentEpoch = 1
	second.Metadata.Ordinal = 2
	in.Messages = append(in.Messages, second)
	in.Cutoff = 2
	now := in.Messages[0].Metadata.CapturedAt.Add(15 * time.Minute)
	opts := DefaultExtractOptions()
	opts.MaxExcerptBytes = 5
	doc, decision, err := GenerateExtract(DefaultConfig(), now, in, opts)
	if err != nil || !decision.Ready {
		t.Fatal(err)
	}
	record, err := SealExtract(doc, Authority{ConsentEpoch: 7, Activation: *in.Activation}, in.Messages, now)
	if err != nil {
		t.Fatal(err)
	}
	return archive.Envelope{Version: 2, Record: record, Metadata: archive.Metadata{Generation: "g", Ordinal: 3, CapturedAt: &now, DerivedKind: archive.DerivedSessionExtract}}, in.Messages, now
}
func TestStoredVerifierAggregatesInputAndReferenceBudgets(t *testing.T) {
	for _, kind := range []string{"input", "references"} {
		t.Run(kind, func(t *testing.T) {
			e, originals, now := storedPairFixture(t)
			body, err := DecodeStored(e)
			if err != nil {
				t.Fatal(err)
			}
			if kind == "input" {
				first, _ := archive.EncodeEnvelope(originals[0])
				second, _ := archive.EncodeEnvelope(originals[1])
				limit := len(first) + 1
				if len(second)+1 > limit {
					limit = len(second) + 1
				}
				body.Document.Manifest.Config.MaxInputBytes = limit
			} else {
				refs, err := json.Marshal(body.Document.Manifest.Sources)
				if err != nil {
					t.Fatal(err)
				}
				body.Document.Manifest.Config.MaxReferenceBytes = len(refs) - 1
			}
			e = reencodeStoredFixture(t, e, body)
			if _, err := DecodeStored(e); err != nil {
				t.Fatal("fixture failed before actual-source aggregate verification", kind, err)
			}
			if _, err := VerifyStored(e, originals, now); !errors.Is(err, ErrInvalidStored) {
				t.Fatal("aggregate proof budget bypassed", kind, err)
			}
		})
	}
}
func TestStoredPairPreservesMixedEpochUnicodeAndEmptySource(t *testing.T) {
	e, originals, now := storedPairFixture(t)
	body, err := VerifyStored(e, originals, now)
	if err != nil || e.Record.ConsentEpoch != 1 || len(body.Document.Excerpts) != 2 || body.Document.Excerpts[0].Text != "🙂" || body.Document.Excerpts[0].End != 4 || !body.Document.Excerpts[0].Truncated || body.Document.Excerpts[1].Text != "" || body.Document.Excerpts[1].Truncated {
		t.Fatal("mixed-epoch/Unicode literal proof wrong", err)
	}
}

type delayedDefaultProofLookup struct {
	*archive.MemStore
	calls int
}

func (s *delayedDefaultProofLookup) LookupEnvelope(r archive.Record) (archive.Envelope, bool, error) {
	s.calls++
	if s.calls == 1 {
		time.Sleep(6 * time.Second)
	}
	return s.MemStore.LookupEnvelope(r)
}
func TestLoadStoredDefaultBudgetStopsAfterOneInFlightOverrun(t *testing.T) {
	e, originals, now := storedPairFixture(t)
	source := &delayedDefaultProofLookup{MemStore: archive.NewMemStore()}
	for _, original := range originals {
		if err := source.PutEnvelope(original); err != nil {
			t.Fatal(err)
		}
	}
	proof, records, err := LoadStored(e, source, now)
	if !errors.Is(err, context.DeadlineExceeded) || source.calls != 1 || proof.Format != "" || len(records) != 0 {
		t.Fatal("default proof budget absent or returned partial evidence", err, source.calls)
	}
}
func TestLoadStoredUnavailableResolverReturnsNoProof(t *testing.T) {
	e, _, now := storedFixture(t)
	proof, records, err := LoadStored(e, nil, now)
	if !errors.Is(err, archive.ErrUnavailable) || proof.Format != "" || len(records) != 0 {
		t.Fatal("unavailable resolver returned proof or wrong failure", err)
	}
}
func TestStoredEmbeddedDocumentBudgetPrecedesResolver(t *testing.T) {
	e, _, now := storedFixture(t)
	body, err := DecodeStored(e)
	if err != nil {
		t.Fatal(err)
	}
	body.Document.Excerpts[0].Text = strings.Repeat("x", (1<<20)+1024)
	e = reencodeStoredFixture(t, e, body)
	if len(e.Record.Text) >= MaxStoredBytes {
		t.Fatal("wrapper bound masks embedded document fixture")
	}
	source := &proofContextLookup{MemStore: archive.NewMemStore()}
	if _, err := DecodeStored(e); !errors.Is(err, ErrInvalidStored) {
		t.Fatal("oversized embedded document structurally admitted", err)
	}
	if _, _, err := LoadStored(e, source, now); !errors.Is(err, ErrInvalidStored) || source.calls != 0 {
		t.Fatal("oversized embedded document reached resolver", err, source.calls)
	}
}
func TestStoredEncodedHeaderRefusesBeforeWholeDocumentCopy(t *testing.T) {
	e, originals, now := storedFixture(t)
	body, err := DecodeStored(e)
	if err != nil {
		t.Fatal(err)
	}
	doc := body.Document
	doc.Excerpts = []Excerpt{}
	doc.Notice = strings.Repeat("\x00", 200000)
	header, err := json.Marshal(doc)
	if err != nil || len(header) <= 1<<20 {
		t.Fatal("encoded header fixture", len(header), err)
	}
	allocated := allocatedExtractBytes(func() {
		if _, err := SealExtract(doc, Authority{ConsentEpoch: body.ConsentEpoch, Activation: body.Activation}, originals, now); err == nil {
			t.Fatal("encoded header crossed complete document bound")
		}
	})
	if allocated > 2<<20 {
		t.Fatalf("copied whole oversized doc after header crossed budget: %d bytes", allocated)
	}
}

type cancelledMissingProofLookup struct {
	*archive.MemStore
	cancel context.CancelFunc
	calls  int
}

func (s *cancelledMissingProofLookup) LookupEnvelope(archive.Record) (archive.Envelope, bool, error) {
	s.calls++
	s.cancel()
	return archive.Envelope{}, false, nil
}
func TestLoadStoredCancellationDominatesInterruptedMissingResult(t *testing.T) {
	e, _, now := storedFixture(t)
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	source := &cancelledMissingProofLookup{MemStore: archive.NewMemStore(), cancel: cancel}
	proof, records, err := LoadStoredContext(ctx, e, source, now)
	if !errors.Is(err, context.Canceled) || source.calls != 1 || proof.Format != "" || len(records) != 0 {
		t.Fatal("cancelled lookup became permanent source absence", err, source.calls)
	}
}

func TestStoredRegressedVerifierClockIsTransientNotInvalidData(t *testing.T) {
	e, originals, now := storedFixture(t)
	for _, clock := range []time.Time{now.Add(-time.Nanosecond), time.Time{}, time.Date(10000, 1, 1, 0, 0, 0, 0, time.UTC)} {
		if _, err := VerifyStored(e, originals, clock); !errors.Is(err, ErrVerifierClock) || errors.Is(err, ErrInvalidStored) {
			t.Fatal("temporary verifier clock became permanent invalidation", err)
		}
	}
	// Malformed relationships inside durable evidence are still permanently invalid.
	at := now.Add(-2 * time.Nanosecond)
	e.Metadata.CapturedAt = &at
	if _, err := VerifyStored(e, originals, now); !errors.Is(err, ErrInvalidStored) {
		t.Fatal("malformed stored time relationship treated transient", err)
	}
}
