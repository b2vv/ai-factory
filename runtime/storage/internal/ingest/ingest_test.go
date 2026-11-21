package ingest

import (
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"sync"
	"testing"

	"aifactory.local/storage/internal/archive"
	"aifactory.local/storage/internal/config"
	"aifactory.local/storage/internal/wal"
)

func bigUsage() config.Usage { return config.Usage{FreeBytes: 1 << 40} } // ample headroom

func newIngestor(t *testing.T, store archive.Store, cfg config.Config) *Ingestor {
	t.Helper()
	ing, err := Open(filepath.Join(t.TempDir(), "wal"), config.NewAccountant(cfg), store)
	if err != nil {
		t.Fatalf("Open: %v", err)
	}
	t.Cleanup(func() { ing.Close() })
	return ing
}

func msg(project, session, message, text string) archive.Record {
	return archive.Record{Project: project, SessionID: session, MessageID: message, Seq: 1,
		Type: archive.TypeMessage, Role: "user", Text: text}
}

// capture -> ingestion (durable WAL) -> drain -> archive -> query.
func TestAcceptDrainQuery(t *testing.T) {
	store := archive.NewMemStore()
	ing := newIngestor(t, store, config.Default())
	if _, err := ing.Accept("k1", msg("p", "s", "m1", "hello world"), bigUsage()); err != nil {
		t.Fatalf("accept: %v", err)
	}
	n, err := ing.Drain()
	if err != nil || n != 1 {
		t.Fatalf("drain: n=%d err=%v", n, err)
	}
	hits, err := ing.Query("p", "hello", "")
	if err != nil || len(hits) != 1 || hits[0].Text != "hello world" {
		t.Fatalf("query: hits=%v err=%v", hits, err)
	}
}

// A replayed delivery with the same idempotency key is a durable no-op; exactly one record
// reaches the archive even across repeated accept + repeated drain.
func TestRedeliveryIdempotent(t *testing.T) {
	store := archive.NewMemStore()
	ing := newIngestor(t, store, config.Default())
	r := msg("p", "s", "m1", "once")
	for i := 0; i < 3; i++ {
		if _, err := ing.Accept("same-key", r, bigUsage()); err != nil {
			t.Fatalf("accept %d: %v", i, err)
		}
	}
	if c, _ := ing.AcceptedCount(); c != 1 {
		t.Fatalf("WAL must dedup identical key to 1 accepted record, got %d", c)
	}
	if _, err := ing.Drain(); err != nil {
		t.Fatalf("drain1: %v", err)
	}
	if _, err := ing.Drain(); err != nil { // re-drain must be idempotent
		t.Fatalf("drain2: %v", err)
	}
	if got := store.All("p"); len(got) != 1 {
		t.Fatalf("exactly one archived record expected, got %d", len(got))
	}
}

// Archive unavailable: Drain fails closed (ErrUnavailable), the accepted record stays
// durable in the WAL, and it drains once the archive recovers. PG is never promoted.
func TestArchiveUnavailableBuffersThenDrains(t *testing.T) {
	store := archive.NewMemStore()
	ing := newIngestor(t, store, config.Default())
	if _, err := ing.Accept("k1", msg("p", "s", "m1", "buffered"), bigUsage()); err != nil {
		t.Fatalf("accept: %v", err)
	}
	store.SetAvailable(false)
	if n, err := ing.Drain(); n != 0 || err != archive.ErrUnavailable {
		t.Fatalf("drain with archive down must be (0, ErrUnavailable), got (%d, %v)", n, err)
	}
	if c, _ := ing.AcceptedCount(); c != 1 {
		t.Fatalf("accepted record must remain durable in the WAL while archive is down, got %d", c)
	}
	store.SetAvailable(true)
	if n, err := ing.Drain(); n != 1 || err != nil {
		t.Fatalf("drain after recovery must commit the buffered record, got (%d, %v)", n, err)
	}
	if len(store.All("p")) != 1 {
		t.Fatalf("buffered record must reach the archive after recovery")
	}
}

// At the WAL/live cap, intake returns backpressure and NOTHING is written (accepted data is
// never evicted to make room).
func TestBackpressureNeverEvicts(t *testing.T) {
	cfg := config.Default()
	cfg.WALBytes = 8 // smaller than any serialized record
	store := archive.NewMemStore()
	ing := newIngestor(t, store, cfg)
	if _, err := ing.Accept("k1", msg("p", "s", "m1", "too big for the tiny WAL cap"), bigUsage()); err == nil {
		t.Fatalf("intake past the WAL bound must be rejected (backpressure)")
	}
	if c, _ := ing.AcceptedCount(); c != 0 {
		t.Fatalf("a rejected intake must write nothing, got %d accepted", c)
	}
}

// Project isolation: a query for one project never returns another project's records.
func TestProjectIsolation(t *testing.T) {
	store := archive.NewMemStore()
	ing := newIngestor(t, store, config.Default())
	if _, err := ing.Accept("a1", msg("proj-A", "s", "m1", "alpha"), bigUsage()); err != nil {
		t.Fatal(err)
	}
	if _, err := ing.Accept("b1", msg("proj-B", "s", "m1", "beta"), bigUsage()); err != nil {
		t.Fatal(err)
	}
	if _, err := ing.Drain(); err != nil {
		t.Fatal(err)
	}
	a, _ := ing.Query("proj-A", "", "")
	b, _ := ing.Query("proj-B", "", "")
	if len(a) != 1 || a[0].Text != "alpha" {
		t.Fatalf("proj-A must see only its record, got %v", a)
	}
	if len(b) != 1 || b[0].Text != "beta" {
		t.Fatalf("proj-B must see only its record, got %v", b)
	}
}

// Crash in the window AFTER the archive commit but BEFORE the watermark is persisted: the
// record is already in the archive; after restart the watermark is still behind, so Drain
// re-commits, and the idempotent store makes that a no-op — no loss and no logical
// duplicate.
func TestCrashAfterCommitBeforeWatermark(t *testing.T) {
	dir := filepath.Join(t.TempDir(), "wal")
	store := archive.NewMemStore()
	ing, err := Open(dir, config.NewAccountant(config.Default()), store)
	if err != nil {
		t.Fatal(err)
	}
	if _, err := ing.Accept("k1", msg("p", "s", "m1", "v"), bigUsage()); err != nil {
		t.Fatal(err)
	}
	orig := writeWatermark
	writeWatermark = func(string, uint64) error { return fmt.Errorf("injected crash before watermark fsync") }
	n, derr := ing.Drain()
	writeWatermark = orig
	if n != 0 || derr == nil {
		t.Fatalf("drain must report the checkpoint failure after the commit, got n=%d err=%v", n, derr)
	}
	if len(store.All("p")) != 1 {
		t.Fatalf("record must already be in the archive (committed before the simulated crash)")
	}
	ing.Close()

	// Restart: watermark was never written, so Drain re-commits; idempotent store => 1 record.
	ing2, err := Open(dir, config.NewAccountant(config.Default()), store)
	if err != nil {
		t.Fatalf("reopen: %v", err)
	}
	defer ing2.Close()
	if _, err := ing2.Drain(); err != nil {
		t.Fatalf("re-drain after restart: %v", err)
	}
	if got := store.All("p"); len(got) != 1 {
		t.Fatalf("after restart exactly one record (no loss, no duplicate), got %d", len(got))
	}
}

// ambiguousStore durably stores the record but returns an error to the caller on the first
// Put (archive wrote data, client saw a timeout/error). The retry must be safe.
type ambiguousStore struct {
	*archive.MemStore
	failNext bool
}

func (a *ambiguousStore) Put(r archive.Record) error {
	_ = a.MemStore.Put(r) // durably written despite the error we are about to return
	if a.failNext {
		a.failNext = false
		return fmt.Errorf("timeout after durable write")
	}
	return nil
}

func TestAmbiguousCommitRetrySafe(t *testing.T) {
	store := &ambiguousStore{MemStore: archive.NewMemStore(), failNext: true}
	ing := newIngestor(t, store, config.Default())
	if _, err := ing.Accept("k1", msg("p", "s", "m1", "v"), bigUsage()); err != nil {
		t.Fatal(err)
	}
	if n, err := ing.Drain(); n != 0 || err == nil {
		t.Fatalf("first drain hit the ambiguous commit; expected (0, err), got (%d, %v)", n, err)
	}
	if len(store.All("p")) != 1 {
		t.Fatalf("record was durably written despite the error")
	}
	// Retry: the record is re-Put; idempotent store => still exactly one; watermark advances.
	if n, err := ing.Drain(); n != 1 || err != nil {
		t.Fatalf("retry drain must be safe, got (%d, %v)", n, err)
	}
	if len(store.All("p")) != 1 {
		t.Fatalf("retry must not duplicate, got %d", len(store.All("p")))
	}
}

// A corrupt watermark (bad CRC) must fail closed on open rather than being trusted (which
// could silently skip uncommitted records).
func TestWatermarkCorruptionFailsClosed(t *testing.T) {
	dir := filepath.Join(t.TempDir(), "wal")
	store := archive.NewMemStore()
	ing, err := Open(dir, config.NewAccountant(config.Default()), store)
	if err != nil {
		t.Fatal(err)
	}
	if _, err := ing.Accept("k1", msg("p", "s", "m1", "v"), bigUsage()); err != nil {
		t.Fatal(err)
	}
	if _, err := ing.Drain(); err != nil {
		t.Fatal(err)
	}
	ing.Close()
	// Corrupt the checkpoint: a large committed with a bogus CRC.
	if err := os.WriteFile(filepath.Join(dir, "committed.seq"), []byte(`{"committed":999,"crc":1}`), 0o600); err != nil {
		t.Fatal(err)
	}
	if _, err := Open(dir, config.NewAccountant(config.Default()), store); err == nil {
		t.Fatalf("a CRC-invalid watermark must fail closed on open, not be trusted")
	}
}

// Concurrent/batch Drain must commit each record exactly once and never skip past an
// uncommitted record (the checkpoint advances only after a confirmed commit).
func TestConcurrentDrainNoSkipNoDup(t *testing.T) {
	store := archive.NewMemStore()
	ing := newIngestor(t, store, config.Default())
	for i, k := range []string{"k1", "k2", "k3"} {
		if _, err := ing.Accept(k, msg("p", "s", fmt.Sprintf("m%d", i), fmt.Sprintf("v%d", i)), bigUsage()); err != nil {
			t.Fatal(err)
		}
	}
	var wg sync.WaitGroup
	for i := 0; i < 5; i++ {
		wg.Add(1)
		go func() { defer wg.Done(); _, _ = ing.Drain() }()
	}
	wg.Wait()
	if got := store.All("p"); len(got) != 3 {
		t.Fatalf("each of 3 records must be committed exactly once under concurrent drain, got %d", len(got))
	}
}

// Same identity with a different payload remains a conflict surfaced by Drain, never a
// silent "successful replay".
func TestIngestSameIDDifferentPayloadConflict(t *testing.T) {
	store := archive.NewMemStore()
	ing := newIngestor(t, store, config.Default())
	if _, err := ing.Accept("k1", msg("p", "s", "m1", "foo"), bigUsage()); err != nil {
		t.Fatal(err)
	}
	// Same archive identity (p/s/m1), different payload, even under a DISTINCT WAL key: the
	// canonical-identity index (V2-3) now surfaces the conflict PRE-ADMISSION (ErrKeyConflict),
	// so it never becomes a durable WAL record that would poison the drain. (The archive Put's
	// ErrIDConflict remains as defense in depth for any record that reaches it.)
	if _, err := ing.Accept("k2", msg("p", "s", "m1", "bar"), bigUsage()); !errors.Is(err, wal.ErrKeyConflict) {
		t.Fatalf("different payload under same identity must conflict pre-admission, got %v", err)
	}
	// The first record drains cleanly; the conflict never overwrote it.
	if _, err := ing.Drain(); err != nil {
		t.Fatalf("drain of the first record must succeed (conflict was rejected pre-admission): %v", err)
	}
	if got := store.All("p"); len(got) != 1 || got[0].Text != "foo" {
		t.Fatalf("conflict must not overwrite; expected one record 'foo', got %v", got)
	}
}

// A quarantined (gate-denied) record must not be published, must stay durable in the WAL
// (retained, not lost), and must NOT block a later allowed record of a DIFFERENT project
// from draining. The checkpoint advances past the quarantined record.
func TestDrainGatedQuarantineDoesNotBlockOthers(t *testing.T) {
	store := archive.NewMemStore()
	ing := newIngestor(t, store, config.Default())
	if _, err := ing.Accept("k1", msg("proj-A", "s", "m1", "deny me"), bigUsage()); err != nil {
		t.Fatal(err)
	}
	if _, err := ing.Accept("k2", msg("proj-B", "s", "m1", "allow me"), bigUsage()); err != nil {
		t.Fatal(err)
	}
	// Gate denies proj-A (e.g. barred), allows everything else.
	gate := func(r archive.Record) bool { return r.Project != "proj-A" }
	n, err := ing.DrainGated(gate)
	if err != nil || n != 1 {
		t.Fatalf("exactly the allowed record must publish, got n=%d err=%v", n, err)
	}
	if len(store.All("proj-A")) != 0 {
		t.Fatalf("quarantined proj-A record must NOT be published")
	}
	if got := store.All("proj-B"); len(got) != 1 || got[0].Text != "allow me" {
		t.Fatalf("allowed proj-B record must publish despite the earlier quarantine, got %v", got)
	}
	// The quarantined record is still durable in the WAL (retained, not lost).
	if c, _ := ing.AcceptedCount(); c != 2 {
		t.Fatalf("both records remain durable in the WAL, got %d", c)
	}
	// Checkpoint advanced past both: a re-drain publishes nothing new and is not blocked.
	if n, err := ing.DrainGated(gate); err != nil || n != 0 {
		t.Fatalf("re-drain must publish nothing new and not block, got n=%d err=%v", n, err)
	}
}

// Query fails closed when the archive is unavailable (never an empty "no history").
func TestQueryFailClosed(t *testing.T) {
	store := archive.NewMemStore()
	ing := newIngestor(t, store, config.Default())
	store.SetAvailable(false)
	if _, err := ing.Query("p", "", ""); err != archive.ErrUnavailable {
		t.Fatalf("query with archive down must fail closed, got %v", err)
	}
}
