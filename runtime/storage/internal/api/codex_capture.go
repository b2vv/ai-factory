package api

import (
	"aifactory.local/storage/internal/capture"
	"io"
	"net/http"
)

// Explicit capture-authorized transport for selected documented events, not a hook installer.
func (s *Server) handleCaptureCodexEvent(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		writeErr(w, http.StatusMethodNotAllowed, "POST required")
		return
	}
	if s.ing == nil || !s.cfg.CaptureEnabled {
		writeErr(w, 503, "capture is not enabled")
		return
	}
	project, source := r.URL.Query().Get("project"), r.URL.Query().Get("source_instance")
	if !s.requireCapture(w, r, project) {
		return
	}
	body, err := io.ReadAll(http.MaxBytesReader(w, r.Body, 1<<20))
	if err != nil {
		writeErr(w, 400, "Codex event body unreadable or too large")
		return
	}
	recs, red, err := capture.AdaptCodexEvent(body, project, source)
	if err != nil {
		writeErr(w, 400, err.Error())
		return
	}
	s.ingestRecords(w, r, project, capture.CodexEventProvider, recs, red)
}
