package api

import (
	"aifactory.local/storage/internal/archive"
	"aifactory.local/storage/internal/authz"
	"aifactory.local/storage/internal/control"
	"aifactory.local/storage/internal/registry"
	"aifactory.local/storage/internal/search"
	"encoding/json"
	"errors"
	"net/http"
	"net/url"
	"strconv"
	"time"
	"unicode/utf8"
)

type timeCursor struct {
	Field, Since string
	Checkpoint   search.Checkpoint
	Upper        int64
	After        *search.TimePosition
}
type timedHit struct {
	archive.Record
	CapturedAt      *time.Time `json:"captured_at"`
	SourceEventTime *time.Time `json:"source_event_time"`
}

func validRecentBinding(state control.ArchiveState, current search.Checkpoint, cursor timeCursor, project string) bool {
	c := cursor.Checkpoint
	return state.MigrationComplete && c.Project == project && current.Project == project && c.SourceGeneration == state.Generation && current.SourceGeneration == c.SourceGeneration && c.PolicyRevision == strconv.FormatUint(state.PolicyRevision, 10) && current.PolicyRevision == c.PolicyRevision && current.ProjectionGeneration == c.ProjectionGeneration && cursor.Upper >= 0 && cursor.Upper <= state.CommittedOrdinal && cursor.Upper <= c.Ordinal && current.Ordinal >= cursor.Upper
}
func (s *Server) handleRecentSearch(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		writeErr(w, 405, "GET required")
		return
	}
	q, err := url.ParseQuery(r.URL.RawQuery)
	allowed := map[string]bool{"project": true, "q": true, "provider": true, "sort": true, "time_field": true, "since": true, "cursor": true}
	if err != nil {
		writeErr(w, 400, "invalid time query")
		return
	}
	for key, values := range q {
		if !allowed[key] || len(values) != 1 || !utf8.ValidString(values[0]) || len(values[0]) > 8192 {
			writeErr(w, 400, "unique bounded time-query parameters required")
			return
		}
	}
	project, query, provider := q.Get("project"), q.Get("q"), q.Get("provider")
	if project == "" || len(project) > 4096 || len(query) > 4096 || len(provider) > 4096 || (q.Get("sort") != "" && q.Get("sort") != "recent") {
		writeErr(w, 400, "bounded project/query and sort=recent required")
		return
	}
	field := q.Get("time_field")
	if field == "" {
		field = "source_event_time"
	}
	if field != "source_event_time" && field != "captured_at" {
		writeErr(w, 400, "unknown time field")
		return
	}
	var since *time.Time
	canonicalSince := ""
	if q.Get("since") != "" {
		parsed, err := time.Parse(time.RFC3339Nano, q.Get("since"))
		if err != nil {
			writeErr(w, 400, "since must be RFC3339 with timezone")
			return
		}
		value := parsed.UTC()
		if value.Year() < 0 || value.Year() > 9999 {
			writeErr(w, 400, "since UTC year out of range")
			return
		}
		since = &value
		canonicalSince = value.Format(time.RFC3339Nano)
	}
	if err := authz.Authorize(s.ctl.Registry(), s.agentToken(r), project, registry.OpSearch); err != nil {
		writeErr(w, 403, err.Error())
		return
	}
	if s.searchStore == nil || s.ing == nil {
		writeErr(w, 503, "time index unavailable")
		return
	}
	source, ok := s.ing.Store().(archive.MetadataStore)
	if !ok {
		writeErr(w, 503, "source metadata unavailable")
		return
	}
	state, active, err := s.ctl.ArchiveState(project)
	if err != nil || !active || !state.MigrationComplete {
		writeErr(w, 503, "metadata migration required")
		return
	}
	current, found, err := s.searchStore.Checkpoint(project)
	if err != nil || !found {
		writeErr(w, 503, "time index checkpoint unavailable")
		return
	}
	cursor := timeCursor{Field: field, Since: canonicalSince, Checkpoint: current, Upper: state.CommittedOrdinal}
	if raw := q.Get("cursor"); raw != "" {
		decoded, err := s.decodeCursor(raw)
		if err != nil || decoded.Time == nil || decoded.Project != recentBinding(project) || decoded.Query != recentBinding(query) || decoded.Provider != recentBinding(provider) || decoded.Time.Field != field || decoded.Time.Since != canonicalSince {
			writeErr(w, 400, "invalid or mismatched time cursor")
			return
		}
		cursor = *decoded.Time
		cursor.Checkpoint.Project = project
	} else if !current.Complete || current.Ordinal != state.CommittedOrdinal {
		writeErr(w, 503, "index is behind committed source; retry when caught up")
		return
	}
	if !validRecentBinding(state, current, cursor, project) {
		writeErr(w, 409, "time cursor generation changed; restart query")
		return
	}
	window, readErr := s.searchStore.TimeWindow(cursor.Checkpoint, field, since, cursor.After, cursor.Upper, query)
	hits := []timedHit{}
	next := window.Next
	used := 0
	incomplete := false
	if readErr == nil {
		for _, ref := range window.References {
			identity, err := sourceIdentity(ref.Identity, project)
			if err != nil {
				readErr = err
				break
			}
			e, found, err := source.LookupEnvelope(identity)
			if err != nil {
				readErr = err
				break
			}
			if !found {
				incomplete = true
				continue
			}
			digest, err := search.MetadataHash(e)
			if err != nil {
				readErr = err
				break
			}
			stamp := e.Metadata.SourceEventTime
			if field == "captured_at" {
				stamp = e.Metadata.CapturedAt
			}
			if search.RecordHash(e.Record) != ref.PayloadHash || digest != ref.MetadataHash || e.Metadata.Generation != cursor.Checkpoint.SourceGeneration || e.Metadata.Ordinal != ref.Ordinal || stamp == nil || search.TimestampKey(*stamp) != ref.Time {
				incomplete = true
				continue
			}
			if provider != "" && e.Record.Provider != provider {
				continue
			}
			hit := timedHit{Record: e.Record, CapturedAt: e.Metadata.CapturedAt, SourceEventTime: e.Metadata.SourceEventTime}
			raw, err := json.Marshal(hit)
			if err != nil {
				readErr = err
				break
			}
			if len(raw) > archive.ScanBytes {
				readErr = archive.ErrRecordTooLarge
				break
			}
			if used+len(raw) > archive.ScanBytes {
				next = ref.Before
				break
			}
			used += len(raw)
			hits = append(hits, hit)
		}
	}
	s.withArchiveWriter(w, project, func(w http.ResponseWriter, tx *control.ArchiveTransaction) {
		if err := authz.Authorize(s.ctl.Registry(), s.agentToken(r), project, registry.OpSearch); err != nil {
			writeErr(w, 403, err.Error())
			return
		}
		if tx == nil {
			writeErr(w, 409, "archive generation unavailable")
			return
		}
		latest, err := tx.State()
		if err != nil {
			writeErr(w, 503, "archive authority unavailable")
			return
		}
		checkpoint, found, err := s.searchStore.Checkpoint(project)
		if err != nil {
			writeErr(w, 503, "time index unavailable")
			return
		}
		if !found || !validRecentBinding(latest, checkpoint, cursor, project) || errors.Is(readErr, search.ErrCheckpoint) {
			writeErr(w, 409, "time cursor generation changed; restart query")
			return
		}
		if readErr != nil {
			writeErr(w, 503, "time index or authoritative source unavailable")
			return
		}
		visible := []timedHit{}
		for _, hit := range hits {
			if len(s.ctl.Retention().Serve([]archive.Record{hit.Record}, "capture")) == 1 {
				visible = append(visible, hit)
			}
		}
		token := ""
		if next != nil {
			cursor.After = next
			token, err = s.encodeCursor(pageCursor{Project: project, Query: query, Provider: provider, Time: &cursor})
			if err != nil {
				writeErr(w, 503, "continuation unavailable")
				return
			}
		}
		snippetRecords := make([]archive.Record, 0, len(visible))
		for _, hit := range visible {
			snippetRecords = append(snippetRecords, hit.Record)
		}
		writeJSON(w, 200, map[string]any{"project": project, "search_mode": "tokenized_simple_nfc_casefold", "sort": "recent", "time_field": field, "since": canonicalSince, "unknown_times": "excluded", "hits": visible, "snippets": sourceSnippets(snippetRecords, query, true), "next_cursor": token, "derived": true, "total_exact": false, "incomplete": incomplete, "consistency": "committed_upper_bound_live_authorization"})
	})
}
