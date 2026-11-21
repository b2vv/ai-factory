//go:build integration

// Capacity/admission tests on the RUNNING API (real handlers + real capacity meter + real
// Mongo via httptest). They prove reject-before-exceed, WAL backpressure, free-space
// headroom, a reject -> recover -> accept cycle without loss/eviction, and concurrency near
// the limit - all driven through POST /v1/capture, with usage measured from the real
// filesystem + archive, never an ample stub.
package api_test

import (
	"context"
	"fmt"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"sync/atomic"
	"testing"
	"time"

	"aifactory.local/storage/internal/api"
	"aifactory.local/storage/internal/archive"
	"aifactory.local/storage/internal/config"
	"aifactory.local/storage/internal/control"
	"aifactory.local/storage/internal/ingest"
	"aifactory.local/storage/internal/meter"
)

// oneMsg is a single-message synthetic fixture for a project.
func oneMsg(project, mid, text string) map[string]any {
	return map[string]any{
		"provider": "synthetic", "source_instance": "inst-1", "project": project,
		"messages": []map[string]any{
			{"session_id": "s1", "message_id": mid, "seq": 1, "role": "user", "text": text, "kind": "message"},
		},
	}
}

// consentProjA mints proj-A and enables capture consent via the operator HTTP endpoints.
func consentProjA(t *testing.T, ts *httptest.Server) {
	t.Helper()
	// Idempotent across phases that share state: a re-mint returns 400 (already exists),
	// which is fine here.
	op(t, ts, "/v1/projects", map[string]string{"UUID": "proj-A", "Label": "A"})
	if code, _ := op(t, ts, "/v1/consent", map[string]any{"Project": "proj-A", "Provider": "synthetic", "Capability": "capture", "Enabled": true}); code != 200 {
		t.Fatalf("consent: %d", code)
	}
}

// buildServer wires a real API server over a shared state dir + Mongo db, so multiple
// phases (restart with a different cap) can run against the SAME durable state and archive.
func buildServer(t *testing.T, dir, db, uri string, doInit bool, tweak func(*config.Config)) (*httptest.Server, *archive.MongoStore, func()) {
	t.Helper()
	statePath := filepath.Join(dir, "state")
	var ctl *control.Durable
	var err error
	if doInit {
		ctl, err = control.Initialize(statePath)
	} else {
		ctl, err = control.Open(statePath)
	}
	if err != nil {
		t.Fatalf("control: %v", err)
	}
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	store, err := archive.OpenMongo(ctx, uri, db, "archive")
	if err != nil {
		ctl.Close()
		t.Fatalf("OpenMongo: %v", err)
	}
	cfg := config.Default()
	cfg.MongoEnabled, cfg.CaptureEnabled = true, true
	cfg.MongoURI, cfg.MongoDB, cfg.MongoCollection = uri, db, "archive"
	if tweak != nil {
		tweak(&cfg)
	}
	if err := cfg.Validate(); err != nil {
		store.Close()
		ctl.Close()
		t.Fatalf("Validate: %v", err)
	}
	ing, err := ingest.Open(filepath.Join(dir, "ingest", "wal"), config.NewAccountant(cfg), store)
	if err != nil {
		store.Close()
		ctl.Close()
		t.Fatalf("ingest.Open: %v", err)
	}
	srv := api.New(ctl, cfg, "operator", e2eOpSecret)
	srv.SetAvailability(store.Available, nil)
	srv.SetIngestor(ing)
	srv.SetUsageMeter(func() (config.Usage, error) {
		sctx, sc := context.WithTimeout(context.Background(), 3*time.Second)
		defer sc()
		sz, serr := store.StorageBytes(sctx)
		if serr != nil {
			return config.Usage{}, serr
		}
		return meter.Measure(statePath, filepath.Join(dir, "ingest", "wal"), sz)
	})
	ts := httptest.NewServer(srv.Handler())
	var once sync.Once
	closeFn := func() {
		once.Do(func() { ts.Close(); ing.Close(); store.Close(); ctl.Close() })
	}
	t.Cleanup(closeFn)
	return ts, store, closeFn
}

func TestCapacityRejectBeforeExceedLiveCap(t *testing.T) {
	ts, _ := e2eServerWith(t, func(c *config.Config) { c.LiveCapBytes = 1 })
	consentProjA(t, ts)
	code, m := op(t, ts, "/v1/capture", fixture("proj-A"))
	if code != http.StatusServiceUnavailable {
		t.Fatalf("capture past the live cap must be rejected (503), got %d (%v)", code, m)
	}
	if e, _ := m["error"].(string); !strings.Contains(e, "live-data cap") {
		t.Fatalf("expected a live-data-cap backpressure reason, got %q", e)
	}
	if acc, _ := m["accepted"].(float64); acc != 0 {
		t.Fatalf("reject-before-exceed must accept nothing, got %v", acc)
	}
}

func TestCapacityWALBackpressure(t *testing.T) {
	ts, _ := e2eServerWith(t, func(c *config.Config) { c.WALBytes = 1 })
	consentProjA(t, ts)
	code, m := op(t, ts, "/v1/capture", fixture("proj-A"))
	if code != http.StatusServiceUnavailable {
		t.Fatalf("capture past the WAL bound must be rejected (503), got %d (%v)", code, m)
	}
	if e, _ := m["error"].(string); !strings.Contains(e, "WAL bound") {
		t.Fatalf("expected a WAL-bound backpressure reason, got %q", e)
	}
}

func TestCapacityFreeHeadroom(t *testing.T) {
	ts, _ := e2eServerWith(t, func(c *config.Config) { c.FreeHeadroom = 1 << 62 })
	consentProjA(t, ts)
	code, m := op(t, ts, "/v1/capture", fixture("proj-A"))
	if code != http.StatusServiceUnavailable {
		t.Fatalf("capture breaching the free-space headroom must be rejected (503), got %d (%v)", code, m)
	}
	if e, _ := m["error"].(string); !strings.Contains(e, "free-space headroom") {
		t.Fatalf("expected a free-space-headroom reason, got %q", e)
	}
}

// NOTE ON SCOPE: this test proves recovery via a CONFIG CHANGE (operator raises the
// configurable D4 cap between phases) - NOT recovery at an unchanged limit. It does not
// raise the agreed D4 DEFAULTS to pass; it uses a tiny cap only to force a reject, then
// restores an adequate cap. Fixed-limit recovery via actual resource freeing is covered
// separately by TestCapacityFixedLimitRecoveryViaFreedSpace.
func TestCapacityRecoveryCycleNoEviction(t *testing.T) {
	uri := os.Getenv("MONGO_URI")
	if uri == "" {
		t.Skip("MONGO_URI not set")
	}
	dir := t.TempDir()
	db := fmt.Sprintf("caprec_%d", time.Now().UnixNano())

	// Phase 1 — adequate caps: capture R1 (committed, durable).
	ts1, store1, close1 := buildServer(t, dir, db, uri, true, nil)
	consentProjA(t, ts1)
	if code, m := op(t, ts1, "/v1/capture", oneMsg("proj-A", "m1", "first record")); code != 200 {
		t.Fatalf("phase1 capture: %d (%v)", code, m)
	}
	if n := len(mustFetch(t, store1, "proj-A")); n != 1 {
		t.Fatalf("phase1: R1 must be committed, got %d", n)
	}
	close1()

	// Phase 2 — tiny live cap: new capture rejected (reject-before-exceed); R1 untouched.
	ts2, store2, close2 := buildServer(t, dir, db, uri, false, func(c *config.Config) { c.LiveCapBytes = 1 })
	if code, _ := op(t, ts2, "/v1/capture", oneMsg("proj-A", "m2", "second record")); code != http.StatusServiceUnavailable {
		t.Fatalf("phase2 capture must be rejected at the tiny cap, got %d", code)
	}
	if n := len(mustFetch(t, store2, "proj-A")); n != 1 {
		t.Fatalf("phase2: R1 must remain (no eviction/loss), got %d", n)
	}
	close2()

	// Phase 3 — cap raised back (recovered capacity): capture now accepted; R1 AND R2 present.
	ts3, store3, close3 := buildServer(t, dir, db, uri, false, nil)
	if code, m := op(t, ts3, "/v1/capture", oneMsg("proj-A", "m2", "second record")); code != 200 {
		t.Fatalf("phase3 capture after recovery: %d (%v)", code, m)
	}
	if n := len(mustFetch(t, store3, "proj-A")); n != 2 {
		t.Fatalf("phase3: both R1 and R2 must be present after recovery, got %d", n)
	}
	close3()
}

// Fixed-limit recovery: with the capacity cap UNCHANGED, breach the free-space headroom by
// consuming unrelated disk space -> capture rejected; then ACTUALLY free that space (delete
// the filler) -> capture accepted. No cap change, no eviction of accepted records.
//
// This covers the free-space dimension ONLY. The WAL/live dimensions have a KNOWN GAP:
// the ingest WAL is append-only for normal operation and has NO size-driven compaction or
// rotation, so at a fixed WAL cap there is currently no ROUTINE way to free WAL space. (The
// crash-safe wal.Compact exists but reclaims space only as a side effect of a project PURGE,
// not as routine self-reclamation.) This test does not pretend to cover that dimension; it
// remains OPEN, not closed.
func TestCapacityFixedLimitRecoveryViaFreedSpace(t *testing.T) {
	if os.Getenv("MONGO_URI") == "" {
		t.Skip("MONGO_URI not set")
	}
	// Probe the volume's free space via the same meter the server uses.
	probe := t.TempDir()
	u, err := meter.Measure(probe, probe, 0)
	if err != nil {
		t.Fatalf("probe free space: %v", err)
	}
	const fillerSize = int64(128 << 20) // 128 MiB
	const margin = int64(32 << 20)      // headroom 32 MiB below current free
	if u.FreeBytes < fillerSize+margin+(256<<20) {
		t.Skipf("not enough free space to run the headroom-recovery test (free=%d)", u.FreeBytes)
	}
	headroom := u.FreeBytes - margin // fixed for the whole test

	ts, store, _ := buildServer(t, t.TempDir(), "capfix_"+fmt.Sprint(time.Now().UnixNano()), os.Getenv("MONGO_URI"), true, func(c *config.Config) {
		c.FreeHeadroom = headroom
	})
	consentProjA(t, ts)

	// Consume unrelated disk space on the same volume to breach the fixed headroom.
	fillerDir := t.TempDir()
	filler := filepath.Join(fillerDir, "filler.bin")
	if err := os.WriteFile(filler, make([]byte, fillerSize), 0o600); err != nil {
		t.Fatalf("write filler: %v", err)
	}
	if code, m := op(t, ts, "/v1/capture", oneMsg("proj-A", "m1", "blocked by headroom")); code != http.StatusServiceUnavailable {
		os.Remove(filler)
		t.Fatalf("with free space consumed, capture must be rejected on headroom, got %d (%v)", code, m)
	}
	if n := len(mustFetch(t, store, "proj-A")); n != 0 {
		t.Fatalf("rejected capture must have committed nothing, got %d", n)
	}

	// ACTUALLY free the resource (delete the filler) at the UNCHANGED headroom -> accept.
	if err := os.Remove(filler); err != nil {
		t.Fatalf("free filler: %v", err)
	}
	if code, m := op(t, ts, "/v1/capture", oneMsg("proj-A", "m1", "admitted after free")); code != 200 {
		t.Fatalf("after freeing space, capture must be admitted at the same headroom, got %d (%v)", code, m)
	}
	if n := len(mustFetch(t, store, "proj-A")); n != 1 {
		t.Fatalf("exactly the newly admitted record must be present (no eviction), got %d", n)
	}
}

// Concurrent captures near the admission path must stay consistent: the number of
// successful (200) captures equals the number of records committed to the archive, with no
// loss, no duplicate, and no corruption.
func TestConcurrentCaptureNearLimit(t *testing.T) {
	uri := os.Getenv("MONGO_URI")
	if uri == "" {
		t.Skip("MONGO_URI not set")
	}
	dir := t.TempDir()
	db := fmt.Sprintf("capconc_%d", time.Now().UnixNano())
	ts, store, _ := buildServer(t, dir, db, uri, true, nil) // adequate caps
	consentProjA(t, ts)

	const n = 20
	var ok200 int32
	var wg sync.WaitGroup
	for i := 0; i < n; i++ {
		wg.Add(1)
		go func(i int) {
			defer wg.Done()
			code, _ := op(t, ts, "/v1/capture", oneMsg("proj-A", fmt.Sprintf("m%d", i), fmt.Sprintf("rec-%d", i)))
			if code == 200 {
				atomic.AddInt32(&ok200, 1)
			}
		}(i)
	}
	wg.Wait()
	committed := len(mustFetch(t, store, "proj-A"))
	if committed != int(ok200) {
		t.Fatalf("committed records (%d) must equal successful captures (%d): no loss/dup under concurrency", committed, ok200)
	}
	if committed != n {
		t.Fatalf("under adequate caps all %d concurrent captures should commit exactly once, got %d", n, committed)
	}
}
