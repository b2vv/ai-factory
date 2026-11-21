package api

import (
	"aifactory.local/storage/internal/capture"
	"io"
	"net/http"
)

// Explicit capture-authorized transport for selected documented events, not a hook installer.
func (s *Server) handleCaptureCodexEvent(w http.ResponseWriter, r *http.Request) {
	s.handleCodexEvent(w, r, false)
}

func (s *Server) handleCaptureCodexSnapshot(w http.ResponseWriter, r *http.Request) {
	s.handleCodexEvent(w, r, true)
}

func (s *Server) handleCodexEvent(w http.ResponseWriter, r *http.Request, snapshots bool) {
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
	adapt, provider := capture.AdaptCodexEvent, capture.CodexEventProvider
	if snapshots {
		adapt, provider = capture.AdaptCodexSnapshotEvent, capture.CodexSnapshotProvider
	}
	recs, red, err := adapt(body, project, source)
	if err != nil {
		writeErr(w, 400, err.Error())
		return
	}
	if snapshots {
		w.Header().Set("X-AF-Codex-Contract", "2")
	}
	s.ingestRecords(w, r, project, provider, recs, red)
}
