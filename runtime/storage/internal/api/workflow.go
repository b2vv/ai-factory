package api

import (
	"aifactory.local/storage/internal/authz"
	"aifactory.local/storage/internal/config"
	"aifactory.local/storage/internal/control"
	"aifactory.local/storage/internal/registry"
	"aifactory.local/storage/internal/workflow"
	"encoding/json"
	"errors"
	"io"
	"math"
	"net/http"
)

func (s *Server) SetWorkflowStore(store workflow.Store) { s.workflowStore = store }
func (s *Server) reservationTotal() int64 {
	n := s.workflowReserved.Load() + s.indexReserved.Load() + s.ctl.ReservedBytes()
	if s.ing != nil {
		n += s.ing.ReservationBytes()
	}
	return n
}
func (s *Server) handleWorkflowTask(w http.ResponseWriter, r *http.Request) {
	if s.workflowStore == nil {
		writeErr(w, 503, "workflow backend not enabled")
		return
	}
	project, id := r.URL.Query().Get("project"), r.URL.Query().Get("id")
	if project == "" || id == "" {
		writeErr(w, 400, "project and stable task id required")
		return
	}
	op := registry.OpWorkflowRead
	if r.Method == http.MethodPut {
		op = registry.OpWorkflowWrite
	} else if r.Method != http.MethodGet {
		writeErr(w, 405, "GET or PUT required")
		return
	}
	if e := authz.Authorize(s.ctl.Registry(), s.agentToken(r), project, op); e != nil {
		writeErr(w, 403, e.Error())
		return
	}
	if r.Method == http.MethodGet {
		task, found, readErr := s.workflowStore.Get(project, id)
		s.withAuthority(w, func(w http.ResponseWriter) {
			if e := authz.Authorize(s.ctl.Registry(), s.agentToken(r), project, op); e != nil {
				writeErr(w, 403, e.Error())
				return
			}
			if readErr != nil {
				writeErr(w, 503, "workflow read failed")
				return
			}
			if !found {
				writeErr(w, 404, "task not found")
				return
			}
			owner, epoch, ok := s.ctl.Registry().WorkflowAuthority(project)
			if !ok {
				writeErr(w, 403, "unknown project authority")
				return
			}
			writeJSON(w, 200, map[string]any{"project": project, "task": task, "authority": owner, "epoch": epoch, "derived_stale": owner != registry.OwnerPostgres})
		})
		return
	}
	var body struct {
		ExpectedVersion int64             `json:"expected_version"`
		Epoch           int64             `json:"epoch"`
		Fields          map[string]string `json:"fields"`
	}
	dec := json.NewDecoder(http.MaxBytesReader(w, r.Body, 1<<20))
	dec.DisallowUnknownFields()
	if e := dec.Decode(&body); e != nil {
		writeErr(w, 400, "invalid bounded workflow request")
		return
	}
	var extra any
	if e := dec.Decode(&extra); e != io.EOF {
		writeErr(w, 400, "one request required")
		return
	}
	if body.ExpectedVersion < 0 || body.ExpectedVersion == math.MaxInt64 || body.Epoch < 1 {
		writeErr(w, 400, "nonnegative version and positive authority epoch required")
		return
	}
	if s.measure == nil {
		writeErr(w, 503, "capacity metering unavailable")
		return
	}
	base := s.reservationTotal()
	usage, e := s.measure()
	if e != nil {
		writeErr(w, 503, "capacity measurement failed")
		return
	}
	cost, e := workflow.ReservationBytes(project, []workflow.Task{{ID: id, Version: body.ExpectedVersion + 1, Fields: body.Fields}})
	if e != nil {
		writeErr(w, 400, "invalid task")
		return
	}
	s.withAuthority(w, func(w http.ResponseWriter) {
		if e := authz.Authorize(s.ctl.Registry(), s.agentToken(r), project, op); e != nil {
			writeErr(w, 403, e.Error())
			return
		}
		delta := s.reservationTotal() - base
		if s.ing != nil {
			delta += s.ing.PendingArchiveBytes()
		}
		usage.LiveBytes += delta
		usage.FreeBytes -= delta
		// This serialized reservation prevents cross-request stale measurement reuse.
		// Physical PostgreSQL page/index amplification still requires a proven backend
		// bound; encoded task bytes alone are NOT evidence of the strict D4 live cap.
		usage.WALBytes = 0 // workflow CAS does not append to the ingest WAL
		admission := config.NewAccountant(s.cfg).AdmitGrowth(usage, 0, cost)
		if !admission.Allowed {
			writeErr(w, 503, admission.Reason)
			return
		}
		if e := s.ctl.ReserveExternalBytes(cost); e != nil {
			writeErr(w, 503, "durable capacity reservation refused")
			return
		}
		e := workflow.New(s.ctl.Registry(), s.workflowStore).Write(project, id, body.ExpectedVersion, body.Epoch, body.Fields)
		if e != nil {
			if errors.Is(e, workflow.ErrStaleVersion) || errors.Is(e, workflow.ErrStaleEpoch) || errors.Is(e, workflow.ErrNotPGOwned) || errors.Is(e, workflow.ErrVersionConflict) {
				if finishErr := s.ctl.FinishExternal(); finishErr != nil {
					writeErr(w, 503, "accounting reconciliation required")
					return
				}
				writeErr(w, 409, e.Error())
			} else {
				writeErr(w, 503, "workflow write failed; inspect current version before retry")
			}
			return
		}
		if e := s.ctl.FinishExternal(); e != nil {
			writeErr(w, 503, "workflow committed; accounting reconciliation required")
			return
		}
		writeJSON(w, 200, map[string]any{"project": project, "id": id, "version": body.ExpectedVersion + 1, "epoch": body.Epoch})
	})
}

// handleWorkflowCutover is an explicit operator action, not a capture side effect.
// The file path names an operator-mounted dedicated source in the server namespace.
func (s *Server) handleWorkflowCutover(w http.ResponseWriter, r *http.Request) {
	if !s.requireOperator(w, r) {
		return
	}
	store, ok := s.workflowStore.(workflow.SnapshotStore)
	if !ok {
		writeErr(w, 503, "workflow snapshot backend unavailable")
		return
	}
	var body struct {
		Project       string                 `json:"project"`
		Document      string                 `json:"document"`
		Revision      string                 `json:"revision"`
		To            registry.WorkflowOwner `json:"to"`
		ExpectedEpoch int64                  `json:"expected_epoch"`
		EditsFrozen   bool                   `json:"edits_frozen"`
	}
	dec := json.NewDecoder(http.MaxBytesReader(w, r.Body, 16384))
	dec.DisallowUnknownFields()
	if e := dec.Decode(&body); e != nil {
		writeErr(w, 400, "invalid bounded cutover request")
		return
	}
	var extra any
	if e := dec.Decode(&extra); e != io.EOF || !body.EditsFrozen || body.ExpectedEpoch < 1 || body.Project == "" || (body.To != registry.OwnerMarkdown && body.To != registry.OwnerPostgres) {
		writeErr(w, 400, "explicit project, destination, epoch and edit freeze required")
		return
	}
	s.withMutation(w, func(w http.ResponseWriter) {
		_, epoch, known := s.ctl.Registry().WorkflowAuthority(body.Project)
		if !known || epoch != body.ExpectedEpoch {
			writeErr(w, 409, "workflow authority epoch changed")
			return
		}
		receipt, e := workflow.Cutover(s.ctl, store, s.operatorPrincipal(), body.Project, body.Document, body.Revision, body.To)
		if e != nil {
			if errors.Is(e, control.ErrPersistence) || errors.Is(e, control.ErrBlocked) || errors.Is(e, control.ErrCapacity) {
				mutationError(w, e)
			} else if errors.Is(e, workflow.ErrBlockedPGDown) {
				writeErr(w, 503, "workflow backend unavailable; cutover BLOCKED")
			} else {
				writeErr(w, 409, "cutover verification failed; authority not transferred")
			}
			return
		}
		writeJSON(w, 200, receipt)
	})
}
