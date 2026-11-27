package budgetenv

import (
	"context"
	"errors"
	"path/filepath"
	"sync"
	"sync/atomic"
	"testing"
	"time"

	"aifactory.local/storage/internal/budget"
	"aifactory.local/storage/internal/config"
)

const testKey = "archive:test"

// fakeBackends is a scripted backend inventory: each pass returns total (or err)
// and may block until released.
type fakeBackends struct {
	mu      sync.Mutex
	total   int64
	err     error
	gate    chan struct{} // non-nil: a pass waits for it (or its context)
	entered chan struct{} // receives once per pass that started
	calls   atomic.Int64
}

func (f *fakeBackends) pass(ctx context.Context) (map[string]int64, error) {
	f.calls.Add(1)
	f.mu.Lock()
	gate, entered, total, err := f.gate, f.entered, f.total, f.err
	f.mu.Unlock()
	if entered != nil {
		entered <- struct{}{}
	}
	if gate != nil {
		select {
		case <-gate:
		case <-ctx.Done():
			return nil, ctx.Err()
		}
	}
	if err != nil {
		return nil, err
	}
	return map[string]int64{testKey: total, testKey + ":pending": 0}, nil
}

func (f *fakeBackends) set(total int64, err error) {
	f.mu.Lock()
	f.total, f.err = total, err
	f.mu.Unlock()
}

func newTestEnv(t *testing.T, f *fakeBackends) *Environment {
	t.Helper()
	dir := t.TempDir()
	cfg := config.Default()
	cfg.FreeHeadroom = 0
	if e := Initialize(dir, cfg); e != nil {
		t.Fatal(e)
	}
	l, e := budget.Open(filepath.Join(dir, "budget.bin"), nil)
	if e != nil {
		t.Fatal(e)
	}
	env := &Environment{State: dir, Ledger: l, limit: cfg.LiveCapBytes, walLimit: cfg.WALBytes, mongoKey: testKey, backends: f.pass}
	l.SetSampler(env.Sample)
	t.Cleanup(env.Close)
	return env
}

// serveWithoutLoop enters cached mode with no background loop, so a test
// drives every pass itself through refresh.
func serveWithoutLoop(env *Environment) error {
	env.measureMu.Lock()
	env.serving = true
	env.measureMu.Unlock()
	return env.refresh(context.Background())
}

func fixClock(t *testing.T) *time.Time {
	t.Helper()
	now := time.Unix(10_000, 0)
	clock = func() time.Time { return now }
	t.Cleanup(func() { clock = time.Now })
	return &now
}

func component(t *testing.T, env *Environment) int64 {
	t.Helper()
	s, e := env.Sample()
	if e != nil {
		t.Fatal(e)
	}
	return s.Components[testKey]
}

// Acceptance 1: once a measurement exists, admission (Usage) and ledger
// reservations answer at once while a slow pass is still running.
func TestCachedMeasurementDoesNotWaitForASlowPass(t *testing.T) {
	now := fixClock(t)
	f := &fakeBackends{total: 1000}
	env := newTestEnv(t, f)
	if e := env.ServeCached(nil); e != nil {
		t.Fatal(e)
	}
	gate, entered := make(chan struct{}), make(chan struct{}, 4)
	f.mu.Lock()
	f.gate, f.entered = gate, entered
	f.mu.Unlock()
	defer close(gate)
	*now = now.Add(refreshEvery) // due: the next Sample asks for a background pass
	if v := component(t, env); v != 1000 {
		t.Fatalf("cached value expected, got %d", v)
	}
	select {
	case <-entered:
	case <-time.After(5 * time.Second):
		t.Fatal("a due measurement did not start in the background")
	}
	// The pass is now blocked. Everything on the capture path must still answer.
	done := make(chan error, 1)
	go func() {
		if _, e := env.Usage(); e != nil {
			done <- e
			return
		}
		if e := env.Ledger.Reserve(budget.Evidence{Kind: "ingest", KeyHash: "k"}, 10); e != nil {
			done <- e
			return
		}
		done <- env.Ledger.Finish()
	}()
	select {
	case e := <-done:
		if e != nil {
			t.Fatal(e)
		}
	case <-time.After(2 * time.Second):
		t.Fatal("capture-path accounting waited for the background measurement")
	}
	if n := f.calls.Load(); n != 2 {
		t.Fatalf("request path ran backend passes: %d calls", n)
	}
}

// Acceptance 2: no measurement, a failed one or a too old one refuses (fail-closed).
func TestCachedMeasurementRefusesWhenNoneIsFresh(t *testing.T) {
	now := fixClock(t)
	f := &fakeBackends{err: errors.New("backend down")}
	env := newTestEnv(t, f)
	if e := serveWithoutLoop(env); e == nil {
		t.Fatal("a failed first pass must be reported")
	}
	if _, e := env.Usage(); !errors.Is(e, ErrNoMeasurement) {
		t.Fatalf("no measurement must refuse: %v", e)
	}
	if e := env.Ledger.Reserve(budget.Evidence{Kind: "ingest", KeyHash: "k"}, 1); !errors.Is(e, ErrNoMeasurement) {
		t.Fatalf("ledger reservation without a measurement must refuse: %v", e)
	}
	f.set(1000, nil)
	if e := env.refresh(context.Background()); e != nil {
		t.Fatal(e)
	}
	if _, e := env.Usage(); e != nil {
		t.Fatalf("fresh measurement must admit: %v", e)
	}
	// A pass that ran out of time keeps the previous measurement while it is fresh.
	f.set(0, context.DeadlineExceeded)
	if e := env.refresh(context.Background()); !errors.Is(e, context.DeadlineExceeded) {
		t.Fatal(e)
	}
	if _, e := env.Usage(); e != nil {
		t.Fatalf("timed-out refresh must keep a fresh measurement: %v", e)
	}
	// ... but not past the maximum age.
	*now = now.Add(maxMeasurementAge)
	if _, e := env.Usage(); !errors.Is(e, ErrNoMeasurement) {
		t.Fatalf("stale measurement must refuse: %v", e)
	}
	// Any other failure drops the measurement at once.
	f.set(1000, nil)
	if e := env.refresh(context.Background()); e != nil {
		t.Fatal(e)
	}
	f.set(0, errors.New("workflow: invalid metadata inventory"))
	if e := env.refresh(context.Background()); e == nil {
		t.Fatal("refresh error expected")
	}
	if _, e := env.Usage(); !errors.Is(e, ErrNoMeasurement) {
		t.Fatalf("an integrity failure must drop the measurement: %v", e)
	}
	// A clock that moved back cannot make an old measurement look fresh forever.
	f.set(1000, nil)
	if e := env.refresh(context.Background()); e != nil {
		t.Fatal(e)
	}
	*now = now.Add(-time.Minute)
	if _, e := env.Usage(); !errors.Is(e, ErrNoMeasurement) {
		t.Fatalf("measurement from the future must refuse: %v", e)
	}
}

// Acceptance 3: bytes reserved after the measurement's baseline count against
// the budget, including a write reserved before the pass but landing after it.
func TestCachedMeasurementCountsGrowthSinceItsBaseline(t *testing.T) {
	fixClock(t)
	f := &fakeBackends{total: 1000}
	env := newTestEnv(t, f)
	if e := serveWithoutLoop(env); e != nil {
		t.Fatal(e)
	}
	if e := env.Ledger.Reserve(budget.Evidence{Kind: "ingest", KeyHash: "a"}, 500); e != nil {
		t.Fatal(e)
	}
	if e := env.Ledger.Finish(); e != nil {
		t.Fatal(e)
	}
	if v := component(t, env); v != 1500 {
		t.Fatalf("growth since measurement not counted: %d", v)
	}
	if got := env.Ledger.Snapshot().Components[testKey]; got != 1500 {
		t.Fatalf("durable ledger lost the growth: %d", got)
	}
	u, e := env.Usage()
	if e != nil {
		t.Fatal(e)
	}
	// In flight: reserved before the next pass, written after its snapshot.
	if e = env.Ledger.Reserve(budget.Evidence{Kind: "ingest", KeyHash: "b"}, 300); e != nil {
		t.Fatal(e)
	}
	f.set(1500, nil) // the pass sees "a" but not "b"
	if e = env.refresh(context.Background()); e != nil {
		t.Fatal(e)
	}
	if v := component(t, env); v != 1800 {
		t.Fatalf("an in-flight reservation was lost by the refresh: %d", v)
	}
	if e = env.Ledger.Finish(); e != nil {
		t.Fatal(e)
	}
	u2, e := env.Usage()
	if e != nil || u2.LiveBytes != u.LiveBytes+300 {
		t.Fatalf("live usage must grow by the reserved bytes: %d -> %d (%v)", u.LiveBytes, u2.LiveBytes, e)
	}
	// Once a pass observes the write, the growth is not added again.
	f.set(1800, nil)
	if e = env.refresh(context.Background()); e != nil {
		t.Fatal(e)
	}
	if v := component(t, env); v != 1800 {
		t.Fatalf("observed write counted twice after a later pass: %d", v)
	}
}

// Two reservations against one reused measurement cannot both spend the same
// headroom: the second sees the first as growth.
func TestCachedMeasurementCannotBeSpentTwice(t *testing.T) {
	fixClock(t)
	f := &fakeBackends{total: 1000}
	env := newTestEnv(t, f)
	if e := serveWithoutLoop(env); e != nil {
		t.Fatal(e)
	}
	if e := env.Ledger.Refresh(); e != nil {
		t.Fatal(e)
	}
	used := int64(0)
	for _, v := range env.Ledger.Snapshot().Components {
		used += v
	}
	const g = 1 << 20
	if e := env.Ledger.Configure(budget.Policy{LiveCap: used + g + g/2, Headroom: 0, WALCap: config.DefaultWALBytes}); e != nil {
		t.Fatal(e)
	}
	if e := env.Ledger.Reserve(budget.Evidence{Kind: "ingest", KeyHash: "a"}, g); e != nil {
		t.Fatal(e)
	}
	if e := env.Ledger.Finish(); e != nil {
		t.Fatal(e)
	}
	if e := env.Ledger.Reserve(budget.Evidence{Kind: "ingest", KeyHash: "b"}, g); !errors.Is(e, budget.ErrCapacity) {
		t.Fatalf("the same headroom was spent twice: %v", e)
	}
	if n := f.calls.Load(); n != 1 {
		t.Fatalf("reservations measured the backends: %d passes", n)
	}
}

// Outside cached mode (operator commands) every sample still measures now.
func TestUncachedSampleMeasuresEveryTime(t *testing.T) {
	f := &fakeBackends{total: 7}
	env := newTestEnv(t, f)
	component(t, env)
	f.set(9, nil)
	if v := component(t, env); v != 9 || f.calls.Load() != 2 {
		t.Fatalf("uncached sample must measure now: %d after %d passes", v, f.calls.Load())
	}
}

// Close stops the loop even while a pass is blocked.
func TestCloseStopsABlockedRefresh(t *testing.T) {
	now := fixClock(t)
	f := &fakeBackends{total: 1}
	env := newTestEnv(t, f)
	if e := env.ServeCached(nil); e != nil {
		t.Fatal(e)
	}
	entered := make(chan struct{}, 4)
	f.mu.Lock()
	f.gate, f.entered = make(chan struct{}), entered
	f.mu.Unlock()
	*now = now.Add(refreshEvery)
	component(t, env)
	<-entered
	closed := make(chan struct{})
	go func() { env.Close(); close(closed) }()
	select {
	case <-closed:
	case <-time.After(5 * time.Second):
		t.Fatal("Close waited for a blocked measurement")
	}
}
