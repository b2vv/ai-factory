package api_test

import (
	"net/http"
	"net/http/httptest"
	"path/filepath"
	"testing"

	"aifactory.local/storage/internal/api"
	"aifactory.local/storage/internal/archive"
	"aifactory.local/storage/internal/config"
	"aifactory.local/storage/internal/control"
	"aifactory.local/storage/internal/ingest"
	"aifactory.local/storage/internal/wal"
)

// TestPurgeReportsIncompleteWhenUnparseableWALFrameRemains (hermetic; MemStore archive).
//
// A WAL frame whose payload cannot be classified is deliberately KEPT by Compact (rather than
// risk erasing an unrelated project), so a frame that MIGHT belong to the purged project can
// physically remain. This test proves the API does NOT report a clean/complete erasure in that
// case: it returns complete=false with a residual count, while still removing the archive copy
// and RETAINING the deletion barrier.
func TestPurgeReportsIncompleteWhenUnparseableWALFrameRemains(t *testing.T) {
	dir := t.TempDir()
	state := filepath.Join(dir, "state")
	ingWal := filepath.Join(dir, "ingest", "wal")
	initDir(t, state)

	// Inject an unparseable (but CRC-valid) WAL frame BEFORE the Ingestor opens the journal.
	raw, err := wal.Open(ingWal)
	if err != nil {
		t.Fatalf("wal.Open: %v", err)
	}
	if _, err := raw.Accept("k-bad", []byte("<<<not-json>>>")); err != nil {
		t.Fatalf("seed unparseable frame: %v", err)
	}
	raw.Close()

	ctl, err := control.Open(state)
	if err != nil {
		t.Fatalf("control.Open: %v", err)
	}
	t.Cleanup(func() { ctl.Close() })

	store := archive.NewMemStore()
	// An archive copy of the target project exists, so purge has something to remove there.
	_ = store.Put(archive.Record{Project: "proj-A", SourceInstance: "i", SessionID: "s", MessageID: "m", Type: archive.TypeMessage, Role: "user", Text: "x"})

	ing, err := ingest.Open(ingWal, config.NewAccountant(config.Default()), store)
	if err != nil {
		t.Fatalf("ingest.Open: %v", err)
	}
	t.Cleanup(func() { ing.Close() })

	cfg := config.Default()
	cfg.CaptureEnabled = true
	srv := api.New(ctl, cfg, "operator", opSecret)
	srv.SetAvailability(store.Available, nil)
	srv.SetIngestor(ing)
	srv.SetUsageMeter(func() (config.Usage, error) { return config.Usage{FreeBytes: 1 << 40}, nil })
	ts := httptest.NewServer(srv.Handler())
	t.Cleanup(ts.Close)

	if code, _ := do(t, http.MethodPost, ts.URL+"/v1/projects", opHdr(), map[string]string{"UUID": "proj-A", "Label": "A"}); code != 201 {
		t.Fatalf("mint: %d", code)
	}
	// Deletion barrier is required before purge.
	if code, _ := do(t, http.MethodPost, ts.URL+"/v1/barriers/project", opHdr(), map[string]string{"Project": "proj-A"}); code != 200 {
		t.Fatalf("barrier: %d", code)
	}
	code, m := do(t, http.MethodPost, ts.URL+"/v1/purge/project", opHdr(), map[string]string{"Project": "proj-A"})
	if code != 200 {
		t.Fatalf("purge status: %d (%v)", code, m)
	}
	// Archive copy removed, but erasure is NOT complete because an unparseable frame survives.
	if complete, _ := m["complete"].(bool); complete {
		t.Fatalf("purge must report complete=false when an unparseable WAL frame remains: %v", m)
	}
	if res, _ := m["residual_unparseable_wal_frames"].(float64); res < 1 {
		t.Fatalf("expected >=1 residual unparseable WAL frame, got %v", m["residual_unparseable_wal_frames"])
	}
	if ap, _ := m["archive_purged"].(float64); ap != 1 {
		t.Fatalf("archive copy should still be removed, archive_purged=%v", m["archive_purged"])
	}
	if br, _ := m["barrier_retained"].(bool); !br {
		t.Fatalf("deletion barrier must be retained after purge")
	}
	if len(store.All("proj-A")) != 0 {
		t.Fatalf("archive copy must be gone")
	}
	// The unparseable frame physically remains in the WAL (manageable, not silently erased).
	if c, err := ing.AcceptedCount(); err != nil || c != 1 {
		t.Fatalf("unparseable frame must remain in the WAL: count=%d err=%v", c, err)
	}
}
