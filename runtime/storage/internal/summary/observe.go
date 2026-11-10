package summary

import (
	"aifactory.local/storage/internal/archive"
	"context"
	"errors"
	"time"
)

// PreparedSession is a bounded observation, not permission to publish. The writer
// must revalidate Head, policy and every selected original under its authority fence.
type PreparedSession struct {
	Head     *archive.Envelope
	Document ExtractDocument
	Decision Decision
}

// PrepareSession performs read-only work outside the writer fence. A factual
// previous head remains processing progress even when old capture epochs are no
// longer servable. Missing/changed head sources block, never reset the frontier.
func PrepareSession(source archive.SummarySource, q archive.SummaryQuery, key archive.SessionKey, authority Authority, now time.Time, c Config, options ExtractOptions) (PreparedSession, error) {
	return PrepareSessionContext(context.Background(), source, q, key, authority, now, c, options)
}
func PrepareSessionContext(ctx context.Context, source archive.SummarySource, q archive.SummaryQuery, key archive.SessionKey, authority Authority, now time.Time, c Config, options ExtractOptions) (PreparedSession, error) {
	var out PreparedSession
	if ctx == nil {
		return out, errors.New("summary: context required")
	}
	if err := ctx.Err(); err != nil {
		return out, err
	}
	in := Input{Scope: Scope{Project: q.Project, Provider: q.Provider, SourceInstance: key.SourceInstance, SessionID: key.SessionID}, Generation: q.Generation, Cutoff: q.Through, Activation: &authority.Activation}
	version, err := ExtractiveVersion(options)
	if err != nil {
		return out, err
	}
	in.GeneratorVersion = version
	if authority.ConsentEpoch <= 0 || q.ActivationOrdinal != authority.Activation.Ordinal || q.Project != authority.Activation.Project || q.Generation != authority.Activation.Generation {
		return out, ErrInvalidStored
	}
	// Validate caller configuration and scope before any backend access.
	if _, err = Plan(c, now, in); err != nil {
		return out, err
	}
	if source == nil {
		return out, archive.ErrUnavailable
	}
	ready, err := source.SummarySchemaReady()
	if err != nil {
		return out, err
	}
	if !ready {
		return out, errors.New("summary: metadata schema unavailable")
	}
	if err := ctx.Err(); err != nil {
		return out, err
	}
	head, found, err := source.SummaryHead(q, key)
	if err != nil {
		return out, err
	}
	if err := ctx.Err(); err != nil {
		return out, err
	}
	after := q.ActivationOrdinal
	if found {
		// Bind the backend result to this request before any reference resolver IO.
		if head.Record.Project != q.Project || head.Record.Provider != q.Provider || head.Record.SourceInstance != key.SourceInstance || head.Record.SessionID != key.SessionID || head.Metadata.Generation != q.Generation || head.Metadata.Ordinal <= q.ActivationOrdinal || head.Metadata.Ordinal > q.Through {
			return out, ErrInvalidStored
		}
		stored, err := DecodeStored(head)
		if err != nil {
			return out, err
		}
		if stored.ConsentEpoch != authority.ConsentEpoch || stored.Activation != authority.Activation {
			return out, ErrInvalidStored
		}
		if _, _, err = LoadStoredContext(ctx, head, source, now); err != nil {
			return out, err
		}

		refs := stored.Document.Manifest.Sources
		after = refs[len(refs)-1].Metadata.Ordinal
		in.Progress = &Progress{AfterOrdinal: after, PreviousJobID: stored.Document.JobID}
		in.ClockFloor = stored.Document.GeneratedAt
		out.Head = &head
	}
	// At most one crossing page can be observed. This budget cannot stall solely
	// because a complete page takes the observation past the selected-input cap.
	c.MaxObservationBytes = c.MaxInputBytes + archive.ScanBytes + archive.EnvelopeScanRecords
	bytes := 0
	for {
		if err := ctx.Err(); err != nil {
			return PreparedSession{}, err
		}
		page, err := source.ScanSummaryOriginals(q, key, after)
		if err != nil {
			return PreparedSession{}, err
		}
		if err := ctx.Err(); err != nil {
			return PreparedSession{}, err
		}
		if page.More && len(page.Records) == 0 {
			return PreparedSession{}, errors.New("summary: source page made no progress")
		}
		for _, e := range page.Records {
			if e.Metadata.Ordinal <= after || e.Metadata.Ordinal > q.Through {
				return PreparedSession{}, ErrInvalidStored
			}
			raw, err := archive.EncodeEnvelope(e)
			if err != nil {
				return PreparedSession{}, err
			}
			if len(raw)+1 > c.MaxObservationBytes-bytes {
				return PreparedSession{}, errors.New("summary: observation budget exceeded")
			}
			bytes += len(raw) + 1
			in.Messages = append(in.Messages, e)
			after = e.Metadata.Ordinal
		}
		if !page.More {
			in.Complete = true
			break
		}
		if bytes >= c.MaxInputBytes {
			in.Cutoff = after
			in.Complete = true
			break
		}
	}
	if err := ctx.Err(); err != nil {
		return PreparedSession{}, err
	}
	doc, decision, err := GenerateExtract(c, now, in, options)
	if err != nil {
		return PreparedSession{}, err
	}
	out.Document = doc
	out.Decision = decision
	return out, nil
}
