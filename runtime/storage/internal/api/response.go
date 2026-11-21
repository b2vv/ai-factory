package api

import (
	"bytes"
	"fmt"
	"net/http"

	"aifactory.local/storage/internal/registry"
)

const maxBufferedResponse = 16 << 20

type responseSnapshot struct {
	header http.Header
	status int
	body   bytes.Buffer
	failed bool
}

func newResponseSnapshot() *responseSnapshot    { return &responseSnapshot{header: make(http.Header)} }
func (b *responseSnapshot) Header() http.Header { return b.header }
func (b *responseSnapshot) WriteHeader(status int) {
	if b.status == 0 {
		b.status = status
	}
}
func (b *responseSnapshot) Write(p []byte) (int, error) {
	if b.failed || len(p) > maxBufferedResponse-b.body.Len() {
		b.failed = true
		return 0, fmt.Errorf("api: response bound exceeded")
	}
	if b.status == 0 {
		b.status = http.StatusOK
	}
	return b.body.Write(p)
}
func (b *responseSnapshot) emit(w http.ResponseWriter) {
	if b.failed {
		writeErr(w, 503, "response bound exceeded; inspect operation state before retry")
		return
	}
	for k, v := range b.header {
		w.Header()[k] = append([]string(nil), v...)
	}
	status := b.status
	if status == 0 {
		status = http.StatusOK
	}
	w.WriteHeader(status)
	_, _ = w.Write(b.body.Bytes())
}

// withMutation serializes the state transition and JSON snapshot, never transport
// delivery. No actual client ResponseWriter is reachable by the locked callback.
func (s *Server) withMutation(w http.ResponseWriter, action func(http.ResponseWriter)) {
	snapshot := newResponseSnapshot()
	func() { s.mutate.Lock(); defer s.mutate.Unlock(); action(snapshot) }()
	snapshot.emit(w)
}

// withAuthority linearizes final authorization and the immutable response with
// control mutations. Callers do NOT hold mutate. Delivery happens after both locks
// are released: revocation blocks future authorized snapshots, not already queued
// response bytes. Callbacks must not call Durable mutations or nest this fence.
func (s *Server) withAuthority(w http.ResponseWriter, action func(http.ResponseWriter)) {
	s.withMutation(w, func(buffer http.ResponseWriter) {
		err := s.ctl.WithStableAuthority(s.operatorPrincipal(), func(_ *registry.Registry) error { action(buffer); return nil })
		if err != nil {
			writeErr(buffer, 503, "control authority unavailable; retry after recovery")
		}
	})
}
