package api

import (
	"net/http"
	"net/url"
	"unicode/utf8"

	"aifactory.local/storage/internal/archive"
	"aifactory.local/storage/internal/authz"
	"aifactory.local/storage/internal/control"
	"aifactory.local/storage/internal/registry"
)

// handleArchiveMessage retrieves an authoritative record by its existing identity.
// It does not require the derived index or change historical payload/hash bytes.
func (s *Server) handleArchiveMessage(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		writeErr(w, 405, "GET required")
		return
	}
	if s.ing == nil {
		writeErr(w, 503, "archive is not enabled")
		return
	}
	q, parseErr := url.ParseQuery(r.URL.RawQuery)
	if parseErr != nil {
		writeErr(w, 400, "invalid identity query")
		return
	}
	for _, key := range []string{"project", "source_instance", "session_id", "message_id"} {
		values := q[key]
		if len(values) > 1 || !utf8.ValidString(q.Get(key)) || len(q.Get(key)) > 4096 || (key != "source_instance" && q.Get(key) == "") {
			writeErr(w, 400, "unique bounded project, source_instance, session_id and message_id required")
			return
		}
	}
	identity := archive.Record{Project: q.Get("project"), SourceInstance: q.Get("source_instance"), SessionID: q.Get("session_id"), MessageID: q.Get("message_id")}
	if err := authz.Authorize(s.ctl.Registry(), s.agentToken(r), identity.Project, registry.OpArchiveQuery); err != nil {
		writeErr(w, 403, err.Error())
		return
	}
	record, found, err := s.ing.Store().Lookup(identity)
	var prepared preparedSummary
	if err == nil && found {
		prepared, err = s.prepareSummary(record)
	}
	s.withArchiveWriter(w, identity.Project, func(w http.ResponseWriter, tx *control.ArchiveTransaction) {
		if e := authz.Authorize(s.ctl.Registry(), s.agentToken(r), identity.Project, registry.OpArchiveQuery); e != nil {
			writeErr(w, 403, e.Error())
			return
		}
		if err != nil {
			writeErr(w, 503, "archive read failed")
			return
		}
		allowed, policyErr := s.allowPreparedSummary(tx, record, prepared)
		if policyErr != nil {
			writeErr(w, 503, "archive authority unavailable")
			return
		}
		if !found || !allowed {
			writeErr(w, 404, "not_found")
			return
		}
		writeJSON(w, 200, map[string]any{"project": identity.Project, "record": record, "derived": prepared.marked})
	})
}
