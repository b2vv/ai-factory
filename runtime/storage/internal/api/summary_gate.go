package api

import (
	"aifactory.local/storage/internal/archive"
	"aifactory.local/storage/internal/control"
	"aifactory.local/storage/internal/summary"
	"context"
	"errors"
	"reflect"
	"strings"
	"time"
)

type preparedSummary struct {
	text             string
	marked, withheld bool
	authority        control.SummaryActivation
	records          []archive.Record
}

// prepareSummary performs bounded factual verification outside the final policy
// fence. Only the authoritative metadata marker identifies automatic extracts;
// manual summary text and message-ID prefixes are not classification evidence.
func (s *Server) prepareSummary(record archive.Record) (preparedSummary, error) {
	var prepared preparedSummary
	if record.Type != archive.TypeSummary {
		return prepared, nil
	}
	source, ok := s.ing.Store().(archive.MetadataStore)
	if !ok {
		return prepared, nil
	}
	envelope, found, err := source.LookupEnvelope(record)
	if err != nil {
		return prepared, err
	}
	if !found || envelope.Record != record {
		return preparedSummary{withheld: true}, nil
	}
	return s.prepareSummaryEnvelope(envelope, source)
}

func (s *Server) prepareSummaryEnvelope(envelope archive.Envelope, source archive.MetadataStore) (preparedSummary, error) {
	return s.prepareSummaryEnvelopeContext(context.Background(), envelope, source)
}
func (s *Server) prepareSummaryEnvelopeContext(ctx context.Context, envelope archive.Envelope, source archive.MetadataStore) (preparedSummary, error) {
	var prepared preparedSummary
	record := envelope.Record
	if envelope.Metadata.DerivedKind == "" {
		return prepared, nil
	}
	prepared.marked = true
	proof, originals, err := summary.LoadStoredContext(ctx, envelope, source, s.summaryProofNow())
	if err != nil {
		if errors.Is(err, summary.ErrInvalidStored) {
			prepared.withheld = true
			return prepared, nil
		}
		return prepared, err
	}
	parts := make([]string, 0, len(proof.Document.Excerpts))
	for _, excerpt := range proof.Document.Excerpts {
		parts = append(parts, excerpt.Text)
	}
	prepared.text = strings.Join(parts, "\n")
	prepared.authority = control.SummaryActivation{Project: proof.Activation.Project, Provider: record.Provider, Generation: proof.Activation.Generation, Ordinal: proof.Activation.Ordinal, At: proof.Activation.At, ConsentEpoch: proof.ConsentEpoch}
	prepared.records = make([]archive.Record, 0, len(originals)+1)
	prepared.records = append(prepared.records, record)
	for _, source := range originals {
		prepared.records = append(prepared.records, source.Record)
	}
	return prepared, nil
}

func (s *Server) allowPreparedSummary(tx *control.ArchiveTransaction, record archive.Record, prepared preparedSummary) (bool, error) {
	if prepared.withheld {
		return false, nil
	}
	if !prepared.marked {
		return len(s.ctl.Retention().Serve([]archive.Record{record}, "capture")) == 1, nil
	}
	if tx == nil {
		return false, nil
	}
	return tx.SummaryPolicyAllows(prepared.authority, prepared.records)
}

// Inspect at most one TypeSummary per raw page. The next page starts at the last
// fully inspected raw position, including a withheld summary, not a visible hit.
func (s *Server) prepareSummaryWindow(window archive.Window) (archive.Window, map[string]preparedSummary, error) {
	prepared := map[string]preparedSummary{}
	inspected := false
	for i, record := range window.Records {
		if record.Type != archive.TypeSummary {
			continue
		}
		if inspected {
			window.Records = window.Records[:i]
			window.More = true
			break
		}
		inspected = true
		proof, err := s.prepareSummary(record)
		if err != nil {
			return archive.Window{}, nil, err
		}
		prepared[archive.IdentityKey(record)] = proof
	}
	return window, prepared, nil
}
func preparedSnippet(record archive.Record, proof preparedSummary, query string, tokenized bool) snippetReference {
	text := record.Text
	if proof.marked {
		text = proof.text
	}
	snippet := archive.MakeSnippet(text, query, tokenized)
	if proof.marked {
		snippet.Basis = "verified_extract_text:" + snippet.Basis
	}
	return snippetReference{Identity: archive.IdentityKey(record), Snippet: snippet}
}

// One fence-local factual cache avoids resolving the same covered sources again
// during plan/write/readback. Authority is still checked on every invocation.
func (s *Server) publishEnvelopeGate(tx *control.ArchiveTransaction) func(archive.Envelope) (bool, error) {
	return s.publishEnvelopeGateContext(context.Background(), tx)
}
func (s *Server) publishEnvelopeGateContext(ctx context.Context, tx *control.ArchiveTransaction) func(archive.Envelope) (bool, error) {
	source, _ := s.ing.Store().(archive.MetadataStore)
	var last archive.Envelope
	var lastProof preparedSummary
	cached := false
	return func(e archive.Envelope) (bool, error) {
		if err := ctx.Err(); err != nil {
			return false, err
		}
		if e.Metadata.DerivedKind == "" {
			return s.publishGate(e.Record), nil
		}
		proof := lastProof
		// Comparing detached values avoids serializing a hostile oversized body before
		// DecodeStored's cheap admission. Metadata times are compared by value.
		if !cached || e.Version != last.Version || e.Record != last.Record || !reflect.DeepEqual(e.Metadata, last.Metadata) {
			var err error
			proof, err = s.prepareSummaryEnvelopeContext(ctx, e, source)
			if err != nil {
				return false, err
			}
			last, lastProof, cached = e, proof, true
		}
		return s.allowPreparedSummary(tx, e.Record, proof)
	}
}

func (s *Server) summaryProofNow() time.Time {
	if s.summaryProofClock != nil {
		return s.summaryProofClock().UTC()
	}
	return time.Now().UTC()
}
