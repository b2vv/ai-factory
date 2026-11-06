// Package api is the loopback HTTP/JSON surface of the Factory control API (PLAN v4
// section 5). It is a TEST HARNESS entry point, not a supported standalone host distribution:
// the supported delivery is the OCI image + the operator-only Docker-free helper (D1).
//
// Authorization (R4): a supplied project UUID is never authority. Operator-only
// control-registry mutations are authenticated by the bootstrap operator secret
// (delivered to the process by a 0600 token file, never printed). Agent requests carry
// a principal-bound token checked against the registry grant (authz), fail-closed. When
// the durable registry is BLOCKED, mutations are refused (503) and agent auth denies.
package api

import (
	"crypto/subtle"
	"encoding/json"
	"errors"
	"io"
	"net/http"
	"strconv"
	"sync"
	"sync/atomic"
	"time"

	"aifactory.local/storage/internal/archive"
	"aifactory.local/storage/internal/authz"
	"aifactory.local/storage/internal/capture"
	"aifactory.local/storage/internal/config"
	"aifactory.local/storage/internal/control"
	"aifactory.local/storage/internal/health"
	"aifactory.local/storage/internal/ingest"
	"aifactory.local/storage/internal/registry"
	"aifactory.local/storage/internal/retention"
	"aifactory.local/storage/internal/search"
	"aifactory.local/storage/internal/wal"
	"aifactory.local/storage/internal/workflow"
)

// Server wires the durable control registry and config into HTTP handlers.
//
// Mutation serialization (R1/R5/R7): privacy-and-durability-coupled operations must not
// interleave. A single server-level mutation mutex (mutate) is held across the WHOLE of each
// such critical section — capture (gate re-check -> accept -> drain), consent change, barrier
// install, project purge (archive + WAL compaction), and each background-drain cycle — so none
// can bypass another. Lock order is mutate -> control authority -> ingest.mu -> wal internal (never the reverse);
// data admission measures outside mutate, then reconciles shared reservations; control
// persistence measures under its authority fence before writing. The
// the background worker releases mutate during its backoff sleep. The capture gate is
// RE-CHECKED under mutate after measuring, so a revoke/barrier/purge that completed while a
// request was measuring cannot be bypassed.
type Server struct {
	attempts         attemptBook
	searchStore      *search.Store
	searchRequired   bool
	indexAfter       map[string]*archive.Position
	indexProject     int
	indexFailed      atomic.Bool
	indexReserved    atomic.Int64
	workflowStore    workflow.Store
	workflowReserved atomic.Int64
	ctl              *control.Durable
	cfg              config.Config
	opID             string
	opSec            string
	mongoUp          func() bool                  // real archive-backend availability (nil => treated as down)
	pgUp             func() bool                  // real workflow-backend availability (nil => treated as down)
	ing              *ingest.Ingestor             // archive ingestion path (nil when Mongo is disabled)
	measure          func() (config.Usage, error) // live capacity measurement (nil => fail-closed)
	mutate           sync.Mutex                   // serializes capture/consent/barrier/purge/drain (R1/R5/R7)
}

// publishGate is the monotone consent+barrier serve-gate used BOTH by capture drains and the
// background drain worker, so a quarantined (revoked/barred) record is never published by
// either path.
// Caller holds the control authority fence: false means permanent policy denial,
// never temporary BLOCKED authority. Unknown authority stops the drain before IO.
func (s *Server) publishGate(r archive.Record) bool {
	return len(s.ctl.Retention().Serve([]archive.Record{r}, "capture")) == 1
}

// DrainOnce performs one archive-commit drain cycle under the mutation lock, publishing only
// records that pass the serve-gate. It is the single production drain entry point shared by
// the capture path and the background replay worker (R5), so neither can publish while a purge
// holds the lock. It is a no-op when no ingestor is wired; backend failures remain errors.
func (s *Server) DrainOnce() (int, error) {
	if s.ing == nil {
		return 0, nil
	}
	s.mutate.Lock()
	defer s.mutate.Unlock()
	if err := s.recoverArchiveLocked(); err != nil {
		return 0, err
	}
	n := 0
	err := s.ctl.WithStableAuthority(s.operatorPrincipal(), func(_ *registry.Registry) error {
		var e error
		n, e = s.ing.DrainGated(s.publishGate)
		return e
	})
	return n, err
}

// SetIngestor wires the capture ingestion path. When nil, the capture and archive-query
// endpoints report archive unavailable.
func (s *Server) SetIngestor(ing *ingest.Ingestor) { s.ing = ing }

// SetUsageMeter wires the live capacity measurement used for admission. If it is unset or
// returns an error, capture is refused (fail-closed) — a measurement failure is never read
// as unlimited capacity.
func (s *Server) SetUsageMeter(m func() (config.Usage, error)) { s.measure = m }

// SetSharedUsageMeter installs the production meter for control and data writes.
// SetUsageMeter remains the capture-only injection point for tests which pause a
// capture measurement while exercising concurrent authority revocation.
func (s *Server) SetSharedUsageMeter(m func() (config.Usage, error)) {
	s.measure = m
	s.ctl.SetCapacityCheck(func(cost int64) error {
		if m == nil {
			return errors.New("capacity meter unavailable")
		}
		base := s.reservationTotal()
		u, err := m()
		if err != nil {
			return err
		}
		delta := s.reservationTotal() - base
		if s.ing != nil {
			delta += s.ing.PendingArchiveBytes()
		}
		u.LiveBytes += delta
		u.FreeBytes -= delta
		if u.FreeBytes < 0 {
			u.FreeBytes = 0
		}
		// The shared live dimension includes control WAL; the ingest WAL dimension
		// is independently enforced by its owner.
		if a := config.NewAccountant(s.cfg).AdmitGrowth(u, 0, cost); !a.Allowed {
			return errors.New(a.Reason)
		}
		return nil
	})
}

// New builds the API server. operatorID/operatorSecret are the bootstrap operator
// credentials loaded from the 0600 token file by the caller. Backend availability is
// absent by default (reported down) until SetAvailability wires the real stores.
func New(ctl *control.Durable, cfg config.Config, operatorID, operatorSecret string) *Server {
	return &Server{ctl: ctl, cfg: cfg, opID: operatorID, opSec: operatorSecret}
}

// SetAvailability wires the live backend availability probes (refreshed by the composition
// root's pinger) so /health reports the REAL backend state, never a fabricated healthy.
func (s *Server) SetAvailability(mongoUp, pgUp func() bool) {
	s.mongoUp, s.pgUp = mongoUp, pgUp
}

func (s *Server) backendUp() (mongo, pg bool) {
	if s.mongoUp != nil {
		mongo = s.mongoUp()
	}
	if s.pgUp != nil {
		pg = s.pgUp()
	}
	return
}

// Handler returns the HTTP routes.
func (s *Server) Handler() http.Handler {
	mux := http.NewServeMux()
	mux.HandleFunc("/health", s.handleHealth)
	mux.HandleFunc("/v1/projects", s.handleProjects)
	mux.HandleFunc("/v1/grants", s.handleGrants)
	mux.HandleFunc("/v1/grants/revoke", s.handleRevoke)
	mux.HandleFunc("/v1/consent", s.handleConsent)
	mux.HandleFunc("/v1/barriers/project", s.handleBarrierProject)
	mux.HandleFunc("/v1/whoami", s.handleWhoami)
	mux.HandleFunc("/v1/capture", s.handleCapture)
	mux.HandleFunc("/v1/capture/claude-code", s.handleCaptureClaudeCode)
	mux.HandleFunc("/v1/capture/codex-event", s.handleCaptureCodexEvent)
	mux.HandleFunc("/v1/archive/query", s.handleArchiveQuery)
	mux.HandleFunc("/v1/archive/message", s.handleArchiveMessage)
	mux.HandleFunc("/v1/archive/context", s.handleArchiveContext)
	mux.HandleFunc("/v1/archive/freshness", s.handleArchiveFreshness)
	mux.HandleFunc("/v1/search/query", s.handleSearchQuery)
	mux.HandleFunc("/v1/documents/query", s.handleDocumentQuery)
	mux.HandleFunc("GET /v1/ingest/{receipt}", s.handleIngestReceipt)
	mux.HandleFunc("/v1/purge/project", s.handlePurgeProject)
	mux.HandleFunc("/v1/workflow/task", s.handleWorkflowTask)
	mux.HandleFunc("/v1/workflow/cutover", s.handleWorkflowCutover)
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/health" {
			if blocked, _ := s.ctl.Blocked(); blocked {
				writeErr(w, 503, "control authority requires recovery")
				return
			}
		}
		mux.ServeHTTP(w, r)
	})
}

func writeJSON(w http.ResponseWriter, code int, v any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(code)
	_ = json.NewEncoder(w).Encode(v)
}

func writeErr(w http.ResponseWriter, code int, msg string) {
	writeJSON(w, code, map[string]string{"error": msg})
}

// isOperator authenticates the bootstrap operator by constant-time secret comparison.
func (s *Server) isOperator(r *http.Request) bool {
	got := r.Header.Get("X-Operator-Secret")
	if got == "" || s.opSec == "" {
		return false
	}
	return subtle.ConstantTimeCompare([]byte(got), []byte(s.opSec)) == 1
}

func (s *Server) operatorPrincipal() registry.Principal {
	return registry.Principal{ID: s.opID, Kind: registry.Operator}
}

func (s *Server) agentToken(r *http.Request) authz.Token {
	return authz.Token{
		PrincipalID: r.Header.Get("X-Principal-Id"),
		Kind:        registry.Agent,
		Epoch:       parseInt64(r.Header.Get("X-Grant-Epoch")),
		Secret:      r.Header.Get("X-Secret"),
	}
}

func (s *Server) handleHealth(w http.ResponseWriter, r *http.Request) {
	blocked, reason := s.ctl.Blocked()
	mongoUp, pgUp := s.backendUp()
	rep := health.Build(s.cfg, mongoUp, pgUp, blocked, reason)
	// F5: surface the WAL drain backlog (depth), watermark lag, and any ambiguous/damaged
	// regions preserved by a BLOCKED recovery (gaps). Best-effort: a read error here must not
	// take down /health, so it is simply omitted (the rest of the report still serves).
	if s.ing != nil && s.isOperator(r) {
		if p, err := s.ing.Progress(); err == nil {
			rep.Ingestion = &health.Ingestion{
				Accepted: p.Accepted, Processed: p.Processed, Depth: p.Depth,
				HighestSeq: p.HighestSeq, CommittedSeq: p.CommittedSeq, LagSeq: p.LagSeq,
				Blocked: p.Blocked, BlockedRegions: p.BlockedRegions, WALBytes: p.WALBytes,
			}
		}
	}
	if s.isOperator(r) && s.searchRequired {
		rep.Index = &health.Index{Enabled: s.searchStore != nil, LastCycleFailed: s.indexFailed.Load()}
	}
	writeJSON(w, http.StatusOK, rep)
}

// handleIngestReceipt reports the lifecycle state of a single capture receipt / idempotency key
// (F10). Agent-authorized on the ?project= query param (OpArchiveQuery); the receipt is the path
// value. The state is derived from the durable WAL + the archive-committed watermark + archive
// presence; a key belonging to another project reads as not_found (no cross-project leak), and a
// real archive read error surfaces as 503 (never a false state).
func (s *Server) handleIngestReceipt(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		writeErr(w, http.StatusMethodNotAllowed, "GET required")
		return
	}
	if s.ing == nil {
		writeErr(w, http.StatusServiceUnavailable, "archive is not enabled")
		return
	}
	receipt := r.PathValue("receipt")
	if receipt == "" {
		writeErr(w, http.StatusBadRequest, "receipt required")
		return
	}
	project := r.URL.Query().Get("project")
	if project == "" {
		writeErr(w, http.StatusBadRequest, "project query param required")
		return
	}
	if err := authz.Authorize(s.ctl.Registry(), s.agentToken(r), project, registry.OpArchiveQuery); err != nil {
		writeErr(w, http.StatusForbidden, err.Error())
		return
	}
	st, err := s.ing.RecordState(receipt, project)
	var observedSource *archive.Record
	if err == nil && st.State == "archive_committed" {
		source, found, e := s.ing.ArchivedRecord(receipt, project)
		if e != nil {
			err = e
		} else if found {
			observedSource = &source
			if s.searchStore != nil {
				indexed, indexErr := s.searchStore.Matches(source)
				if indexErr != nil {
					st.IndexState = "unavailable"
				} else if indexed {
					st.State = "indexed"
					st.IndexState = "indexed"
				} else {
					st.IndexState = "pending"
				}
			}
		}
	}
	s.withAuthority(w, func(w http.ResponseWriter) {
		if e := authz.Authorize(s.ctl.Registry(), s.agentToken(r), project, registry.OpArchiveQuery); e != nil {
			writeErr(w, 403, e.Error())
			return
		}
		if err != nil {
			writeErr(w, http.StatusServiceUnavailable, "receipt state read failed: "+err.Error())
			return
		}
		st.LifecycleState = st.State
		if observedSource != nil && !s.publishGate(*observedSource) {
			st.LifecycleState = "cancelled"
		}
		if st.State == "not_found" {
			if identity, parseErr := sourceIdentity(receipt, project); parseErr == nil {
				if observed := s.attempts.state(archive.IdentityKey(identity)); observed != "" {
					st.State = observed
					st.LifecycleState = observed
					st.Observation = "ephemeral_request_10m"
				}
			}
		} else if st.State == "quarantined" {
			st.LifecycleState = "cancelled"
		}
		if st.State != "not_found" {
			for _, b := range s.ctl.Retention().Barriers() {
				if b.Project == project && b.Scope == retention.ScopeProject {
					st.LifecycleState = "cancelled"
					break
				}
			}
		}
		writeJSON(w, http.StatusOK, st)
	})
}

func (s *Server) requireOperator(w http.ResponseWriter, r *http.Request) bool {
	if r.Method != http.MethodPost {
		writeErr(w, http.StatusMethodNotAllowed, "POST required")
		return false
	}
	if !s.isOperator(r) {
		writeErr(w, http.StatusUnauthorized, "operator authentication required")
		return false
	}
	return true
}

// mutationError maps control/registry errors to HTTP status codes.
func mutationError(w http.ResponseWriter, err error) {
	if errors.Is(err, control.ErrCapacity) {
		writeJSON(w, 503, map[string]any{"error": err.Error(), "outcome": "not_accepted"})
		return
	}
	if errors.Is(err, control.ErrPersistence) {
		writeJSON(w, 503, map[string]any{"error": err.Error(), "outcome": "unknown"})
		return
	}
	switch err {
	case control.ErrBlocked:
		writeErr(w, http.StatusServiceUnavailable, err.Error())
	case registry.ErrNotOperator:
		writeErr(w, http.StatusForbidden, err.Error())
	default:
		writeErr(w, http.StatusBadRequest, err.Error())
	}
}

func (s *Server) handleProjects(w http.ResponseWriter, r *http.Request) {
	if !s.requireOperator(w, r) {
		return
	}
	var body struct{ UUID, Label string }
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
		writeErr(w, http.StatusBadRequest, "invalid JSON")
		return
	}
	s.withMutation(w, func(w http.ResponseWriter) {
		if err := s.ctl.MintProject(s.operatorPrincipal(), body.UUID, body.Label); err != nil {
			mutationError(w, err)
			return
		}
		writeJSON(w, http.StatusCreated, map[string]string{"uuid": body.UUID})
	})
}

func (s *Server) handleGrants(w http.ResponseWriter, r *http.Request) {
	if !s.requireOperator(w, r) {
		return
	}
	var body struct {
		PrincipalID string   `json:"principal_id"`
		Kind        string   `json:"kind"`
		Projects    []string `json:"projects"`
		Ops         []string `json:"ops"`
		Secret      string   `json:"secret"`
	}
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
		writeErr(w, http.StatusBadRequest, "invalid JSON")
		return
	}
	g := registry.Grant{
		PrincipalID: body.PrincipalID,
		Kind:        registry.PrincipalKind(body.Kind),
		Projects:    map[string]bool{},
		Ops:         map[registry.Op]bool{},
		Secret:      body.Secret,
	}
	for _, p := range body.Projects {
		g.Projects[p] = true
	}
	for _, o := range body.Ops {
		g.Ops[registry.Op(o)] = true
	}
	s.withMutation(w, func(w http.ResponseWriter) {
		if err := s.ctl.IssueGrant(s.operatorPrincipal(), g); err != nil {
			mutationError(w, err)
			return
		}
		stored, _ := s.ctl.Registry().Lookup(body.PrincipalID)
		writeJSON(w, http.StatusCreated, map[string]any{"principal_id": body.PrincipalID, "epoch": stored.Epoch})
	})
}

func (s *Server) handleRevoke(w http.ResponseWriter, r *http.Request) {
	if !s.requireOperator(w, r) {
		return
	}
	var body struct {
		PrincipalID string `json:"principal_id"`
	}
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
		writeErr(w, http.StatusBadRequest, "invalid JSON")
		return
	}
	s.withMutation(w, func(w http.ResponseWriter) {
		if err := s.ctl.RevokeGrant(s.operatorPrincipal(), body.PrincipalID); err != nil {
			mutationError(w, err)
			return
		}
		writeJSON(w, http.StatusOK, map[string]string{"revoked": body.PrincipalID})
	})
}

func (s *Server) handleConsent(w http.ResponseWriter, r *http.Request) {
	if !s.requireOperator(w, r) {
		return
	}
	var body struct {
		Project, Provider, Capability string
		Enabled                       bool
	}
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
		writeErr(w, http.StatusBadRequest, "invalid JSON")
		return
	}
	// Serialize with capture/drain/purge so a revoke cannot land between a capture's gate
	// re-check and its durable accept (R1).
	s.withMutation(w, func(w http.ResponseWriter) {
		epoch, err := s.ctl.SetConsent(s.operatorPrincipal(), body.Project, body.Provider, body.Capability, body.Enabled)
		if err != nil {
			mutationError(w, err)
			return
		}
		writeJSON(w, http.StatusOK, map[string]any{"project": body.Project, "epoch": epoch, "enabled": body.Enabled})
	})
}

func (s *Server) handleBarrierProject(w http.ResponseWriter, r *http.Request) {
	if !s.requireOperator(w, r) {
		return
	}
	var body struct {
		Project string
	}
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
		writeErr(w, http.StatusBadRequest, "invalid JSON")
		return
	}
	// Serialize with capture/drain/purge so a barrier install is atomic w.r.t. a capture's
	// gate re-check (R1).
	s.withMutation(w, func(w http.ResponseWriter) {
		if _, err := s.ctl.DeleteProjectBarrier(s.operatorPrincipal(), body.Project); err != nil {
			mutationError(w, err)
			return
		}
		writeJSON(w, http.StatusOK, map[string]string{"barrier_project": body.Project})
	})
}

// handleWhoami is an agent-scoped read: it authorizes the presented token for the
// requested (project, op) and reports the result. A project-A token asking about project
// B, a revoked/stale token, or a bad secret is denied (fail closed).
func (s *Server) handleWhoami(w http.ResponseWriter, r *http.Request) {
	project := r.URL.Query().Get("project")
	op := registry.Op(r.URL.Query().Get("op"))
	if project == "" || op == "" {
		writeErr(w, http.StatusBadRequest, "project and op query params required")
		return
	}
	s.withAuthority(w, func(w http.ResponseWriter) {
		if err := authz.Authorize(s.ctl.Registry(), s.agentToken(r), project, op); err != nil {
			writeErr(w, http.StatusForbidden, err.Error())
			return
		}
		writeJSON(w, http.StatusOK, map[string]any{
			"principal": r.Header.Get("X-Principal-Id"), "project": project, "op": string(op), "allowed": true,
		})
	})
}

// handleCapture ingests a SYNTHETIC provider fixture (operator-authenticated). It enforces,
// BEFORE any durable accept: the project exists, capture consent for (project, provider) is
// enabled, and no project deletion barrier exists; and it drops prohibited fields via the
// adapter. Accepted records are stamped with the current consent epoch (for the revocation
// cutoff) and drained to the archive.
func (s *Server) handleCapture(w http.ResponseWriter, r *http.Request) {
	if !s.requireOperator(w, r) {
		return
	}
	if s.ing == nil || !s.cfg.CaptureEnabled {
		writeErr(w, http.StatusServiceUnavailable, "capture is not enabled")
		return
	}
	var fx capture.ProviderFixture
	if err := json.NewDecoder(http.MaxBytesReader(w, r.Body, 8<<20)).Decode(&fx); err != nil {
		writeErr(w, http.StatusBadRequest, "invalid JSON")
		return
	}
	if fx.Project == "" || fx.Provider == "" {
		writeErr(w, http.StatusBadRequest, "project and provider are required")
		return
	}
	recs, red := capture.Adapt(fx)
	times := make([]*time.Time, len(fx.Messages))
	for n, m := range fx.Messages {
		times[n] = m.SourceEventTime
	}
	s.ingestRecordsWithTimes(w, fx.Project, fx.Provider, recs, red, times)
}

// handleCaptureClaudeCode ingests a SYNTHETIC Claude Code transcript (JSONL raw body) via
// the provider-specific parser. project and source_instance come from query params; the
// provider is fixed to "claude-code". Same consent/barrier/capacity/redaction gates apply.
func (s *Server) handleCaptureClaudeCode(w http.ResponseWriter, r *http.Request) {
	if !s.requireOperator(w, r) {
		return
	}
	if s.ing == nil || !s.cfg.CaptureEnabled {
		writeErr(w, http.StatusServiceUnavailable, "capture is not enabled")
		return
	}
	project := r.URL.Query().Get("project")
	sourceInstance := r.URL.Query().Get("source_instance")
	if project == "" || sourceInstance == "" {
		writeErr(w, http.StatusBadRequest, "project and source_instance query params are required")
		return
	}
	body, err := io.ReadAll(http.MaxBytesReader(w, r.Body, 8<<20))
	if err != nil {
		writeErr(w, http.StatusBadRequest, "cannot read body")
		return
	}
	recs, red, perr := capture.AdaptClaudeCodeJSONL(body, project, sourceInstance)
	if perr != nil {
		writeErr(w, http.StatusBadRequest, "claude-code transcript parse failed: "+perr.Error())
		return
	}
	s.ingestRecords(w, project, "claude-code", recs, red)
}

// ingestRecords is the shared gate+accept+drain path for any producer of archive records.
// It enforces (project exists, capture consent enabled for project×provider, no project
// deletion barrier), measures capacity (fail-closed), stamps the consent epoch, accepts
// durably, and drains through the publish serve-gate.
//
// R1 ordering: the usage meter is measured FIRST, WITHOUT the mutation lock (it does slow
// backend I/O; holding the lock across it would serialize throughput and could deadlock a
// concurrent purge). The consent+barrier gate is then RE-CHECKED under s.mutate immediately
// before the durable accept, and accept+drain run in the same locked section. So a revoke,
// barrier install, or purge that completed while this request was measuring is observed by the
// re-check (request refused), and once past the re-check no purge/revoke can interleave before
// the write — closing the "capture writes payload after purge" window.
func (s *Server) ingestRecords(w http.ResponseWriter, project, provider string, recs []archive.Record, red []capture.Redaction) {
	s.ingestRecordsWithTimes(w, project, provider, recs, red, nil)
}
func (s *Server) ingestRecordsWithTimes(w http.ResponseWriter, project, provider string, recs []archive.Record, red []capture.Redaction, sourceTimes []*time.Time) {
	if len(sourceTimes) != 0 && len(sourceTimes) != len(recs) {
		writeErr(w, 400, "source time alignment invalid")
		return
	}
	for _, value := range sourceTimes {
		if value != nil && value.IsZero() {
			writeErr(w, 400, "source event time must be known or omitted")
			return
		}
	}

	if !s.ctl.Registry().HasProject(project) {
		writeErr(w, http.StatusBadRequest, "unknown project")
		return
	}
	attemptReceipts, finishAttempt, attemptErr := s.attempts.begin(recs)
	if attemptErr != nil {
		writeErr(w, 503, attemptErr.Error())
		return
	}
	outcome := "failed"
	defer func() { finishAttempt(outcome) }()
	if s.measure == nil {
		writeErr(w, http.StatusServiceUnavailable, "capacity metering is not configured; capture refused (fail-closed)")
		return
	}
	// Snapshot the ingestor's accepted-bytes total BEFORE measuring, then measure once, both
	// BEFORE the mutation lock (fail-closed on error). The growth of the accepted total since
	// this snapshot is what OTHER requests (and earlier records of this same batch) have reserved
	// but which THIS request's measurement does not reflect; it is added back as a reservation
	// under the lock so two concurrently-measured requests cannot both spend the same headroom
	// (V3-1). Snapshotting before the (slow) measurement makes the reservation conservative.
	base := s.reservationTotal()
	u, merr := s.measure()
	if merr != nil {
		writeJSON(w, http.StatusServiceUnavailable, map[string]any{"accepted": 0, "attempt_receipts": attemptReceipts, "error": "capacity measurement failed; capture refused (fail-closed): " + merr.Error()})
		return
	}

	s.withArchiveWriter(w, project, func(w http.ResponseWriter, tx *control.ArchiveTransaction) {
		// RE-CHECK the gate under the lock (authority may have changed while measuring).
		c := s.ctl.Registry().ConsentEpoch(project, provider, "capture")
		if !c.Enabled {
			outcome = "cancelled"
			writeJSON(w, 403, map[string]any{"error": "capture consent is not granted for this project/provider", "attempt_receipts": attemptReceipts})
			return
		}
		for _, b := range s.ctl.Retention().Barriers() {
			if b.Project == project && b.Scope == retention.ScopeProject {
				outcome = "cancelled"
				writeJSON(w, 409, map[string]any{"error": "project has a deletion barrier; capture refused", "attempt_receipts": attemptReceipts})
				return
			}
		}
		if tx != nil {
			for n := range recs {
				recs[n].ConsentEpoch = c.Epoch
			}
			if s.captureMetadata(w, tx, recs, red, attemptReceipts, sourceTimes) {
				outcome = "complete"
			}
			return
		}
		for _, value := range sourceTimes {
			if value != nil {
				writeErr(w, 503, "source event time requires metadata migration")
				return
			}
		}
		accepted := 0
		receipts := []string{}
		for _, rec := range recs {
			rec.ConsentEpoch = c.Epoch
			key := archive.IdentityKey(rec)
			// Reserve everything accepted since THIS request measured (other concurrent requests AND
			// earlier records of this batch) against the shared live/free budget (V2-1 + V3-1). The
			// WAL dimension is reserved exactly inside Accept against the authoritative counter.
			delta := s.reservationTotal() - base
			eff := u
			eff.LiveBytes += delta
			if eff.FreeBytes -= delta; eff.FreeBytes < 0 {
				eff.FreeBytes = 0
			}
			if receipt, err := s.ing.Accept(key, rec, eff); err != nil {
				if receipt.Seq > 0 {
					receipts = append(receipts, key)
				}
				// A same-identity replay with a DIFFERENT payload is a conflict (409), not a
				// silently-dropped duplicate; capacity/other errors stay 503.
				if errors.Is(err, wal.ErrKeyConflict) {
					writeJSON(w, http.StatusConflict, map[string]any{"accepted": accepted, "receipts": receipts, "outcome": "inspect_receipts", "attempt_receipts": attemptReceipts, "error": err.Error()})
					return
				}
				writeJSON(w, http.StatusServiceUnavailable, map[string]any{"accepted": accepted, "receipts": receipts, "outcome": "inspect_receipts", "attempt_receipts": attemptReceipts, "error": err.Error()})
				return
			}
			receipts = append(receipts, key)
			accepted++
		}
		committed, derr := s.ing.DrainGated(s.publishGate)
		resp := map[string]any{"accepted": accepted, "committed": committed, "receipts": receipts, "redactions": red}
		if derr != nil {
			resp["drain_error"] = derr.Error()
		}
		outcome = "complete"
		writeJSON(w, http.StatusOK, resp)
	})
}

// handleArchiveQuery reads back archived records for a project (agent-authorized,
// OpArchiveQuery). It fails closed when the archive is unavailable and applies the retention
// serve-gate (deletion barriers + consent-revocation cutoff) before returning hits.
func (s *Server) handleArchiveQuery(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		writeErr(w, http.StatusMethodNotAllowed, "GET required")
		return
	}
	if s.ing == nil {
		writeErr(w, http.StatusServiceUnavailable, "archive is not enabled")
		return
	}
	project := r.URL.Query().Get("project")
	if project == "" {
		writeErr(w, http.StatusBadRequest, "project query param required")
		return
	}
	if err := authz.Authorize(s.ctl.Registry(), s.agentToken(r), project, registry.OpArchiveQuery); err != nil {
		writeErr(w, http.StatusForbidden, err.Error())
		return
	}
	limit, offset, perr := pageParams(r)
	if perr != nil {
		writeErr(w, 400, perr.Error())
		return
	}
	query, provider := r.URL.Query().Get("q"), r.URL.Query().Get("provider")
	var after *archive.Position
	if raw := r.URL.Query().Get("cursor"); raw != "" {
		c, e := s.decodeCursor(raw)
		if e != nil || c.Time != nil || c.Project != project || c.Query != query || c.Provider != provider || offset != 0 {
			writeErr(w, 400, "invalid or mismatched cursor")
			return
		}
		after = &c.After
	}
	window, err := s.ing.Store().Scan(project, after)
	// Serialize the serve decision with revoke/barrier/purge, after bounded backend IO.
	s.withAuthority(w, func(w http.ResponseWriter) {
		if err := authz.Authorize(s.ctl.Registry(), s.agentToken(r), project, registry.OpArchiveQuery); err != nil {
			writeErr(w, 403, err.Error())
			return
		}
		if err != nil {
			writeErr(w, 503, "archive read failed: "+err.Error())
			return
		}
		hits := archive.Query(s.ctl.Retention().Serve(window.Records, "capture"), query, provider)
		if window.More && offset > 0 && offset >= len(hits) {
			writeErr(w, 400, "offset exceeds bounded window; use cursor pagination")
			return
		}
		lo := offset
		if lo > len(hits) {
			lo = len(hits)
		}
		hi := lo + limit
		if hi > len(hits) {
			hi = len(hits)
		}
		page := hits[lo:hi]
		if page == nil {
			page = []archive.Hit{}
		}
		resp := map[string]any{"project": project, "offset": offset, "limit": limit, "hits": page, "total_exact": false, "consistency": "live_non_snapshot", "total_basis": "observed_authorized_window", "search_mode": "literal_substring_nfc_casefold"}
		snippetRecords := make([]archive.Record, 0, len(page))
		for _, hit := range page {
			snippetRecords = append(snippetRecords, hit.Record)
		}
		resp["snippets"] = sourceSnippets(snippetRecords, query, false)
		if !window.More && after == nil {
			resp["total"] = len(hits)
			resp["observed_matching_count"] = len(hits)
		}
		if hi < len(hits) || window.More {
			var pos archive.Position
			if hi > 0 {
				pos = archive.PositionOf(hits[hi-1].Record)
			} else if len(window.Records) > 0 {
				pos = archive.PositionOf(window.Records[len(window.Records)-1])
			}
			cursor, e := s.encodeCursor(pageCursor{Project: project, Query: query, Provider: provider, After: pos})
			if e != nil {
				writeErr(w, 503, "cursor encoding failed")
				return
			}
			resp["next_cursor"] = cursor
			if !window.More && after == nil {
				resp["next_offset"] = hi
			}
		}
		writeJSON(w, 200, resp)
	})
}

const (
	defaultQueryLimit = 100
	maxQueryLimit     = 1000
)

// pageParams parses the bounded-query pagination inputs. An absent limit uses the default; an
// absent offset is 0. A present value that is not a non-negative integer is a hard error (the
// caller must fix it, not silently receive a different page). limit is clamped DOWN to
// maxQueryLimit so the response size is bounded regardless of the requested value.
func pageParams(r *http.Request) (limit, offset int, err error) {
	limit = defaultQueryLimit
	if v := r.URL.Query().Get("limit"); v != "" {
		n, e := strconv.Atoi(v)
		if e != nil || n <= 0 {
			return 0, 0, errors.New("limit must be a positive integer")
		}
		limit = n
	}
	if limit > maxQueryLimit {
		limit = maxQueryLimit
	}
	if v := r.URL.Query().Get("offset"); v != "" {
		n, e := strconv.Atoi(v)
		if e != nil || n < 0 {
			return 0, 0, errors.New("offset must be a non-negative integer")
		}
		offset = n
	}
	return limit, offset, nil
}

// handlePurgeProject physically erases a project's archived records (operator-only). It
// requires that a project deletion barrier already exists (deletion is a tombstone FIRST,
// then physical erasure - PLAN §11.1); the barrier is retained, so purged content can never
// resurrect via a later drain or a backup restore (both gate on the barrier).
func (s *Server) handlePurgeProject(w http.ResponseWriter, r *http.Request) {
	if !s.requireOperator(w, r) {
		return
	}
	if s.ing == nil {
		writeErr(w, http.StatusServiceUnavailable, "archive is not enabled")
		return
	}
	var body struct{ Project string }
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil || body.Project == "" {
		writeErr(w, http.StatusBadRequest, "project required")
		return
	}
	// Serialize the WHOLE purge (barrier-check -> archive erase -> WAL compaction) with
	// capture/drain so no in-flight capture or background drain can re-materialize a payload
	// after erasure (R1/R5).
	s.withMutation(w, func(w http.ResponseWriter) {
		barred := false
		for _, b := range s.ctl.Retention().Barriers() {
			if b.Project == body.Project && b.Scope == retention.ScopeProject {
				barred = true
				break
			}
		}
		if !barred {
			// Refuse to physically erase without a durable deletion tombstone first.
			writeErr(w, http.StatusConflict, "no project deletion barrier; set a deletion barrier before purge")
			return
		}
		if !s.ing.Store().Available() {
			writeErr(w, http.StatusServiceUnavailable, archive.ErrUnavailable.Error())
			return
		}
		if s.searchRequired && s.searchStore == nil {
			writeErr(w, 503, "managed search index requires PostgreSQL for complete purge")
			return
		}
		n, err := s.ing.Store().Purge(body.Project, "")
		if err != nil {
			writeErr(w, http.StatusServiceUnavailable, "purge failed: "+err.Error())
			return
		}
		if s.searchStore != nil {
			if e := s.searchStore.Purge(body.Project); e != nil {
				writeJSON(w, 503, map[string]any{"project": body.Project, "archive_purged": n, "complete": false, "index_purged": false, "error": "archive removed but derived index erasure failed"})
				return
			}
		}
		// Managed-store deletion has two halves (PLAN §11.1): the archive copy (above) AND the
		// intake journal. Compact removes the purged project's WAL frames so a later re-drain
		// cannot re-materialize the payload; it is fail-closed (refuses a BLOCKED journal) and
		// preserves every other project's records. The retained barrier (required above, and NOT
		// removed here) prevents resurrection.
		// An empty validated journal has no erasure write or staging liability.
		// This also avoids coupling a no-op purge to an in-flight capture meter.
		out := ingest.CompactOutcome{}
		count, cerr := s.ing.AcceptedCount()
		if cerr == nil && count > 0 {
			if s.measure == nil {
				writeJSON(w, 503, map[string]any{"project": body.Project, "archive_purged": n, "complete": false, "error": "WAL staging capacity meter unavailable"})
				return
			}
			usage, measurementErr := s.measure()
			if measurementErr != nil {
				writeJSON(w, 503, map[string]any{"project": body.Project, "archive_purged": n, "complete": false, "error": "WAL staging capacity measurement failed"})
				return
			}
			out, cerr = s.ing.CompactWithUsage(func(rec archive.Record) bool { return rec.Project != body.Project }, usage)
		}
		if cerr != nil {
			// Archive copy already removed but the WAL half failed: report PARTIAL, never success.
			writeJSON(w, http.StatusServiceUnavailable, map[string]any{
				"project": body.Project, "archive_purged": n, "complete": false,
				"error": "archive copy removed but WAL journal compaction failed (fail-closed); purge is INCOMPLETE: " + cerr.Error(),
			})
			return
		}
		// Honest erasure semantics (do NOT overclaim):
		//   - "complete" means removed from the MANAGED stores (archive + WAL journal). It is NOT a
		//     claim of irreversible destruction of every physical copy on the underlying media
		//     (filesystem remnants, snapshots, backups, replicas) - that is out of scope here.
		//   - if any WAL frame could not be classified (corrupt payload) it was KEPT, so a frame
		//     that MIGHT belong to this project physically remains: complete=false, and we say so.
		resp := map[string]any{
			"project": body.Project, "archive_purged": n, "wal_dropped": out.Dropped,
			"complete":         out.ResidualUnparseable == 0,
			"scope":            "removed from managed stores (archive + WAL journal + configured derived index); media-level copies (fs remnants, snapshots, backups, replicas) are out of scope",
			"barrier_retained": true,
			"index_purged":     !s.searchRequired || s.searchStore != nil,
		}
		if out.ResidualUnparseable > 0 {
			resp["residual_unparseable_wal_frames"] = out.ResidualUnparseable
			resp["warning"] = "one or more WAL frames could not be classified and were preserved; target payload may physically remain in the journal, so erasure is NOT complete"
		}
		writeJSON(w, http.StatusOK, resp)
	})
}

func parseInt64(s string) int64 {
	var n int64
	for _, c := range s {
		if c < '0' || c > '9' {
			return 0
		}
		n = n*10 + int64(c-'0')
	}
	return n
}
