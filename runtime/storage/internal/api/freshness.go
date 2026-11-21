package api

import (
	"aifactory.local/storage/internal/authz"
	"aifactory.local/storage/internal/control"
	"aifactory.local/storage/internal/registry"
	"aifactory.local/storage/internal/search"
	"net/http"
	"net/url"
	"strconv"
	"unicode/utf8"
)

func indexFreshness(state *control.ArchiveState, checkpoint *search.Checkpoint, available bool) string {
	if state == nil {
		return "not_activated"
	}
	if !state.MigrationComplete {
		return "migration_incomplete"
	}
	if !available {
		return "unavailable"
	}
	if checkpoint == nil {
		return "building"
	}
	if checkpoint.SourceGeneration == state.Generation && checkpoint.PolicyRevision == strconv.FormatUint(state.PolicyRevision, 10) && checkpoint.Ordinal == state.CommittedOrdinal && checkpoint.Complete {
		return "caught_up"
	}
	return "behind"
}
func (s *Server) handleArchiveFreshness(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		writeErr(w, 405, "GET required")
		return
	}
	q, err := url.ParseQuery(r.URL.RawQuery)
	project := q.Get("project")
	if err != nil || len(q["project"]) != 1 || project == "" || len(project) > 4096 || !utf8.ValidString(project) {
		writeErr(w, 400, "unique bounded project required")
		return
	}
	if err := authz.Authorize(s.ctl.Registry(), s.agentToken(r), project, registry.OpArchiveQuery); err != nil {
		writeErr(w, 403, err.Error())
		return
	}
	s.withArchiveWriter(w, project, func(w http.ResponseWriter, tx *control.ArchiveTransaction) {
		if err := authz.Authorize(s.ctl.Registry(), s.agentToken(r), project, registry.OpArchiveQuery); err != nil {
			writeErr(w, 403, err.Error())
			return
		}
		var state *control.ArchiveState
		if tx != nil {
			value, err := tx.State()
			if err != nil {
				writeErr(w, 503, "archive authority unavailable")
				return
			}
			state = &value
		}
		var checkpoint *search.Checkpoint
		available := s.searchStore != nil && s.ing != nil && s.ing.Store().Available()
		if available && state != nil {
			value, found, err := s.searchStore.Checkpoint(project)
			if err != nil {
				available = false
			} else if found {
				checkpoint = &value
			}
		}
		status := indexFreshness(state, checkpoint, available)
		if tx != nil {
			pending, err := tx.ProjectionPending()
			if err != nil {
				writeErr(w, 503, "archive authority unavailable")
				return
			}
			if pending {
				status = "recovering"
			}
		}
		writeJSON(w, 200, map[string]any{"project": project, "index_state": status, "basis": "committed_source_checkpoint", "capture_completeness": "unknown", "consistency": "observed_under_authority_fence"})
	})
}
