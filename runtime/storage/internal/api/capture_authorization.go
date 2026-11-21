package api

import (
	"aifactory.local/storage/internal/authz"
	"aifactory.local/storage/internal/registry"
	"net/http"
)

// Called once before admission work and again under the archive writer fence.
// The grant covers this project across providers, never reads or administration.
func (s *Server) requireCapture(w http.ResponseWriter, r *http.Request, project string) bool {
	for _, name := range []string{"X-Operator-Secret", "X-Principal-Id", "X-Grant-Epoch", "X-Secret"} {
		if len(r.Header.Values(name)) > 1 {
			writeErr(w, http.StatusBadRequest, "ambiguous capture credentials")
			return false
		}
	}
	if _, present := r.Header["X-Operator-Secret"]; present {
		return s.requireOperator(w, r)
	}
	if err := authz.Authorize(s.ctl.Registry(), s.agentToken(r), project, registry.OpCapture); err != nil {
		writeErr(w, http.StatusForbidden, "capture authorization denied")
		return false
	}
	return true
}

// Backend errors may include connection details. Only the existing operator
// transport receives diagnostics; scoped callers retain status and receipts.
func (s *Server) captureDiagnostic(r *http.Request, err error) string {
	if s.isOperator(r) {
		return err.Error()
	}
	return "capture unavailable; inspect receipts before retry"
}
