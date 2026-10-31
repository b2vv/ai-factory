package api

import (
	"bytes"
	"net/http/httptest"
	"testing"
)

// Pure buffer tests: no network/backpressure scenario or blocked review probe.
func TestResponseSnapshotBoundAndIndependentBytes(t *testing.T) {
	b := newResponseSnapshot()
	payload := []byte("original")
	b.Header().Set("Content-Type", "application/json")
	if _, e := b.Write(payload); e != nil {
		t.Fatal(e)
	}
	copy(payload, []byte("modified"))
	out := httptest.NewRecorder()
	b.emit(out)
	if out.Code != 200 || out.Body.String() != "original" {
		t.Fatal(out.Code, out.Body.String())
	}
	b = newResponseSnapshot()
	b.WriteHeader(200)
	if _, e := b.Write(bytes.Repeat([]byte{'x'}, maxBufferedResponse+1)); e == nil {
		t.Fatal("bound bypassed")
	}
	out = httptest.NewRecorder()
	b.emit(out)
	if out.Code != 503 || out.Body.Len() > 1024 {
		t.Fatal("partial success emitted", out.Code, out.Body.Len())
	}
}
