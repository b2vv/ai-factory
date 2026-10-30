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
	"net/http"

	"aifactory.local/storage/internal/authz"
	"aifactory.local/storage/internal/config"
	"aifactory.local/storage/internal/control"
	"aifactory.local/storage/internal/health"
	"aifactory.local/storage/internal/registry"
)

// Server wires the durable control registry and config into HTTP handlers.
type Server struct {
	ctl    *control.Durable
	cfg    config.Config
	opID   string
	opSec  string
}

// New builds the API server. operatorID/operatorSecret are the bootstrap operator
// credentials loaded from the 0600 token file by the caller.
func New(ctl *control.Durable, cfg config.Config, operatorID, operatorSecret string) *Server {
	return &Server{ctl: ctl, cfg: cfg, opID: operatorID, opSec: operatorSecret}
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
	return mux
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
	rep := health.Build(s.cfg, false /*mongoUp*/, false /*pgUp*/, blocked, reason)
	writeJSON(w, http.StatusOK, rep)
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
	if err := s.ctl.MintProject(s.operatorPrincipal(), body.UUID, body.Label); err != nil {
		mutationError(w, err)
		return
	}
	writeJSON(w, http.StatusCreated, map[string]string{"uuid": body.UUID})
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
	if err := s.ctl.IssueGrant(s.operatorPrincipal(), g); err != nil {
		mutationError(w, err)
		return
	}
	stored, _ := s.ctl.Registry().Lookup(body.PrincipalID)
	writeJSON(w, http.StatusCreated, map[string]any{"principal_id": body.PrincipalID, "epoch": stored.Epoch})
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
	if err := s.ctl.RevokeGrant(s.operatorPrincipal(), body.PrincipalID); err != nil {
		mutationError(w, err)
		return
	}
	writeJSON(w, http.StatusOK, map[string]string{"revoked": body.PrincipalID})
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
	epoch, err := s.ctl.SetConsent(s.operatorPrincipal(), body.Project, body.Provider, body.Capability, body.Enabled)
	if err != nil {
		mutationError(w, err)
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"project": body.Project, "epoch": epoch, "enabled": body.Enabled})
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
	if _, err := s.ctl.DeleteProjectBarrier(s.operatorPrincipal(), body.Project); err != nil {
		mutationError(w, err)
		return
	}
	writeJSON(w, http.StatusOK, map[string]string{"barrier_project": body.Project})
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
	if err := authz.Authorize(s.ctl.Registry(), s.agentToken(r), project, op); err != nil {
		writeErr(w, http.StatusForbidden, err.Error())
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"principal": r.Header.Get("X-Principal-Id"), "project": project, "op": string(op), "allowed": true,
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
