package api

import (
	"aifactory.local/storage/internal/archive"
	"aifactory.local/storage/internal/authz"
	"aifactory.local/storage/internal/registry"
	"encoding/json"
	"net/http"
	"net/url"
	"strconv"
	"unicode/utf8"
)

func (s *Server) handleArchiveContext(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		writeErr(w, 405, "GET required")
		return
	}
	if s.ing == nil {
		writeErr(w, 503, "archive is not enabled")
		return
	}
	q, e := url.ParseQuery(r.URL.RawQuery)
	if e != nil {
		writeErr(w, 400, "invalid identity query")
		return
	}
	for _, key := range []string{"project", "source_instance", "session_id", "message_id"} {
		if len(q[key]) > 1 || !utf8.ValidString(q.Get(key)) || len(q.Get(key)) > 4096 || (key != "source_instance" && q.Get(key) == "") {
			writeErr(w, 400, "unique bounded identity required")
			return
		}
	}
	limit := 10
	if raw, ok := q["limit"]; ok {
		if len(raw) != 1 {
			writeErr(w, 400, "invalid limit")
			return
		}
		limit, e = strconv.Atoi(raw[0])
		if e != nil || limit < 1 || limit > 50 {
			writeErr(w, 400, "limit must be 1..50")
			return
		}
	}
	identity := archive.Record{Project: q.Get("project"), SourceInstance: q.Get("source_instance"), SessionID: q.Get("session_id"), MessageID: q.Get("message_id")}
	if e := authz.Authorize(s.ctl.Registry(), s.agentToken(r), identity.Project, registry.OpArchiveQuery); e != nil {
		writeErr(w, 403, e.Error())
		return
	}
	type outcome struct {
		record archive.Record
		found  bool
		err    error
		size   int
	}
	outcomes := []outcome{}
	seen := map[string]bool{}
	reason := "limit"
	bytes := 0
	next := identity
	for len(outcomes) < limit {
		if seen[next.MessageID] {
			reason = "cycle"
			break
		}
		seen[next.MessageID] = true
		record, found, err := s.ing.Store().Lookup(next)
		encoded, _ := json.Marshal(record)
		outcomes = append(outcomes, outcome{record, found, err, len(encoded)})
		if err != nil || !found {
			reason = "unavailable"
			break
		}
		if bytes+len(encoded) > archive.ScanBytes {
			reason = "byte_limit"
			break
		}
		bytes += len(encoded)
		if record.ParentID == "" {
			reason = "no_parent"
			break
		}
		next.MessageID = record.ParentID
	}
	s.withAuthority(w, func(w http.ResponseWriter) {
		if e := authz.Authorize(s.ctl.Registry(), s.agentToken(r), identity.Project, registry.OpArchiveQuery); e != nil {
			writeErr(w, 403, e.Error())
			return
		}
		records := []archive.Record{}
		size := 0
		for n, o := range outcomes {
			if o.err != nil {
				writeErr(w, 503, "archive read failed")
				return
			}
			if !o.found || len(s.ctl.Retention().Serve([]archive.Record{o.record}, "capture")) == 0 {
				if n == 0 {
					writeErr(w, 404, "not_found")
					return
				}
				reason = "unavailable"
				break
			}
			if size+o.size > archive.ScanBytes {
				reason = "byte_limit"
				break
			}
			size += o.size
			records = append(records, o.record)
		}
		writeJSON(w, 200, map[string]any{"project": identity.Project, "records": records, "derived": false, "order": "anchor_to_parent", "incomplete": true, "stop_reason": reason})
	})
}
