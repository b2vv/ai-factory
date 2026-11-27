// Package budgetenv binds the accounting ledger to production logical inventory.
// It does not own authority: callers must already hold the control state lock.
package budgetenv

import (
	"aifactory.local/storage/internal/meter"
	"context"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"fmt"
	"path/filepath"
	"strings"
	"sync"
	"time"

	"aifactory.local/storage/internal/archive"
	"aifactory.local/storage/internal/budget"
	"aifactory.local/storage/internal/config"
	"aifactory.local/storage/internal/ingest"
	"aifactory.local/storage/internal/workflow"
)

type Environment struct {
	detached              bool
	State                 string
	Ledger                *budget.Ledger
	Mongo                 *archive.MongoStore
	Postgres              *workflow.PGStore
	mongoKey, postgresKey string
	limit                 int64
	walLimit              int64
	cacheMu               sync.Mutex
	mongoInv              inventoryCache[archive.Inventory]
	pgInv                 inventoryCache[workflow.Inventory]

	// Cached mode (ServeCached): the backend inventory is measured off the
	// request path and reused, plus everything reserved since, until it is too old.
	backends   func(context.Context) (map[string]int64, error) // test seam; nil = measureBackends
	measureMu  sync.Mutex
	serving    bool
	last       *measurement
	lastErr    error
	kick       chan struct{}
	stopLoop   context.CancelFunc
	loopDone   chan struct{}
	logf       func(string, ...any)
	refreshing sync.Mutex // one measurement pass at a time
}

// measurement is one completed backend inventory with the ledger baseline taken
// BEFORE its pass started and the time that pass started.
type measurement struct {
	components map[string]int64
	base       int64
	at         time.Time
}

// ErrNoMeasurement is returned in cached mode while no sufficiently fresh
// measurement exists. Admission treats it like any measurement failure (fail-closed).
var ErrNoMeasurement = errors.New("budget: no sufficiently fresh capacity measurement")

// sampleMaxAge bounds how long an unchanged token may stand for an inventory; after
// it a refresh pass rereads only changed rows. fullCheckEvery bounds how long rows that
// were not reread go without the complete validating read.
const (
	sampleMaxAge   = 30 * time.Second
	fullCheckEvery = 10 * time.Minute
)

// Cached mode: a measurement is refreshed in the background every refreshEvery
// and after refreshGrowth reserved bytes; one older than maxMeasurementAge (from
// the start of its pass) is refused. inventoryTimeout bounds one pass and must
// stay well below maxMeasurementAge.
const (
	refreshEvery      = 30 * time.Second
	refreshGrowth     = 4 << 20
	maxMeasurementAge = 15 * time.Minute
	inventoryTimeout  = workflow.InventoryTimeout
)

var clock = time.Now

// inventoryCache keeps one per-row inventory with the change token taken BEFORE the
// pass that built it. An unchanged, fresh token reuses it; otherwise a refresh pass
// rereads only changed rows, and a full read rebuilds it periodically or after any
// error. A failed pass leaves no inventory behind.
type inventoryCache[T any] struct {
	inv        *T
	token      string
	at, fullAt time.Time
}

func (c *inventoryCache[T]) get(token string, pass func(prev *T) (*T, error), total func(*T) int64) (int64, error) {
	now := clock()
	fresh := c.inv != nil && !now.Before(c.at) && !now.Before(c.fullAt)
	if fresh && c.token == token && now.Sub(c.at) < sampleMaxAge {
		return total(c.inv), nil
	}
	var prev *T
	full := !fresh || now.Sub(c.fullAt) >= fullCheckEvery
	if !full {
		prev = c.inv
	}
	c.inv = nil
	inv, err := pass(prev)
	if err != nil {
		return 0, err
	}
	c.inv, c.token, c.at = inv, token, now
	if full {
		c.fullAt = now
	}
	return total(inv), nil
}

// The full binding is hashed, never persisted or printed. Different bindings
// retain earlier durable liabilities; changing credentials cannot refund data.
func binding(kind, raw string) string {
	sum := sha256.Sum256([]byte(raw))
	return kind + ":" + hex.EncodeToString(sum[:])
}

func Initialize(state string, cfg config.Config) error {
	sample := func() (budget.Sample, error) { return budget.LocalSample(state, cfg.LiveCapBytes) }
	l, e := budget.Initialize(filepath.Join(state, "budget.bin"), budget.Policy{LiveCap: cfg.LiveCapBytes, Headroom: cfg.FreeHeadroom, WALCap: cfg.WALBytes}, sample)
	if e != nil {
		return e
	}
	return l.Close()
}

// Open connects read-only schema inspectors before any writing adapter is opened.
// Missing ledgers refuse; explicit first initialization creates them separately.
// cfg=nil is the offline identity/local-document path: bound backend liabilities
// remain durably charged and the persisted policy is not replaced by defaults.
func Open(state string, cfg *config.Config) (*Environment, error) { return open(state, cfg, true) }
func OpenOffline(state string, cfg *config.Config) (*Environment, error) {
	return open(state, cfg, false)
}
func open(state string, cfg *config.Config, configure bool) (*Environment, error) {
	env := &Environment{State: state, walLimit: config.DefaultWALBytes}
	l, e := budget.Open(filepath.Join(state, "budget.bin"), nil)
	if e != nil {
		return nil, e
	}
	env.Ledger = l
	fail := func(e error) (*Environment, error) { env.Close(); return nil, e }
	policy := l.Snapshot().Policy
	env.limit = policy.LiveCap
	if policy.WALCap > 0 {
		env.walLimit = policy.WALCap
	}
	if cfg != nil {
		if configure {
			env.walLimit = cfg.WALBytes
		}
		if configure {
			policy = budget.Policy{LiveCap: cfg.LiveCapBytes, Headroom: cfg.FreeHeadroom, WALCap: cfg.WALBytes}
			env.limit = cfg.LiveCapBytes
		}
		ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
		defer cancel()
		if cfg.MongoEnabled {
			env.Mongo, e = archive.OpenMongoForBudget(ctx, cfg.MongoURI, cfg.MongoDB, cfg.MongoCollection)
			if e != nil {
				return fail(fmt.Errorf("budget: archive inventory unavailable"))
			}
			env.mongoKey = binding("archive", cfg.MongoURI+"\x00"+cfg.MongoDB+"\x00"+cfg.MongoCollection)
		}
		if cfg.PostgresEnabled {
			env.Postgres, e = workflow.OpenPostgresForMaintenance(ctx, cfg.PostgresDSN)
			if e != nil {
				return fail(fmt.Errorf("budget: PostgreSQL inventory unavailable"))
			}
			env.postgresKey = binding("postgres", cfg.PostgresDSN)
		}
	}
	l.SetSampler(env.Sample)
	if env.Postgres != nil {
		pending := l.Snapshot().Pending
		if len(pending) == 1 && pending[0].Evidence.Kind == "archive-index" {
			ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
			found, proofErr := env.Postgres.ProveArchiveIndex(ctx, pending[0].Evidence.KeyHash, pending[0].Evidence.PayloadHash)
			cancel()
			if proofErr != nil {
				return fail(proofErr)
			}
			if found {
				if e = l.Recover(func(budget.Intent) (bool, error) { return true, nil }); e != nil {
					return fail(e)
				}
			}
		}
	}

	if e = budget.RecoverPaths(state, l); e != nil {
		return fail(e)
	}
	if cfg != nil && configure && len(l.Snapshot().Pending) == 0 {
		if e = l.Configure(policy); e != nil {
			return fail(e)
		}
	}
	if len(l.Snapshot().Pending) == 0 {
		if e = l.Refresh(); e != nil {
			return fail(e)
		}
	}
	return env, nil
}

// Sample is the ledger sampler and the base of Usage. Outside cached mode it
// measures the backends now; in cached mode it never touches them (see ServeCached).
func (e *Environment) Sample() (budget.Sample, error) {
	s, err := budget.LocalSample(e.State, e.limit)
	if err != nil {
		return s, err
	}
	if !e.hasBackends() {
		return s, nil
	}
	e.measureMu.Lock()
	serving := e.serving
	e.measureMu.Unlock()
	var components map[string]int64
	if serving {
		components, err = e.cachedComponents()
	} else {
		ctx, cancel := context.WithTimeout(context.Background(), inventoryTimeout)
		components, err = e.measure(ctx)
		cancel()
	}
	if err != nil {
		return s, err
	}
	for key, value := range components {
		s.Components[key] = value
	}
	return s, nil
}

func (e *Environment) hasBackends() bool {
	return e.Mongo != nil || e.Postgres != nil || e.backends != nil
}

func (e *Environment) measure(ctx context.Context) (map[string]int64, error) {
	if e.backends != nil {
		return e.backends(ctx)
	}
	return e.measureBackends(ctx)
}

// measureBackends reads the backend inventories. Pending archive debt is read
// BEFORE the archive inventory: a record committed in between is then counted
// twice (debt and archive), never zero times.
func (e *Environment) measureBackends(ctx context.Context) (map[string]int64, error) {
	e.cacheMu.Lock()
	defer e.cacheMu.Unlock()
	components := map[string]int64{}
	if e.Mongo != nil {
		debt, err := ingest.PendingLogicalBytes(filepath.Join(e.State, "ingest", "wal"), e.walLimit, e.Mongo)
		if err != nil {
			return nil, err
		}
		token := fmt.Sprint(archive.WriteGeneration())
		n, err := e.mongoInv.get(token, func(prev *archive.Inventory) (*archive.Inventory, error) {
			return e.Mongo.Inventory(ctx, e.limit, prev)
		}, func(inv *archive.Inventory) int64 { return inv.Total })
		if err != nil {
			return nil, err
		}
		components[e.mongoKey] = n
		components[e.mongoKey+":pending"] = debt
	}
	if e.Postgres != nil {
		token, err := e.Postgres.WALPosition(ctx)
		if err != nil {
			return nil, err
		}
		n, err := e.pgInv.get(token, func(prev *workflow.Inventory) (*workflow.Inventory, error) {
			return e.Postgres.Inventory(ctx, e.limit, prev)
		}, func(inv *workflow.Inventory) int64 { return inv.Total })
		if err != nil {
			return nil, err
		}
		components[e.postgresKey] = n
	}
	return components, nil
}

// growthKey is the component that carries bytes reserved since the reused
// measurement. Folding them into an existing component keeps the durable
// ledger's key set unchanged; the next measurement replaces the value.
func (e *Environment) growthKey() string {
	if e.mongoKey != "" {
		return e.mongoKey
	}
	return e.postgresKey
}

// cachedComponents returns the last measurement plus every byte the ledger
// reserved since its baseline. It never waits for a pass: with no measurement,
// or one older than maxMeasurementAge, it refuses and asks for a refresh.
func (e *Environment) cachedComponents() (map[string]int64, error) {
	e.measureMu.Lock()
	m, lastErr := e.last, e.lastErr
	e.measureMu.Unlock()
	if m == nil {
		e.requestRefresh()
		if lastErr != nil {
			return nil, fmt.Errorf("%w (last refresh failed: %v)", ErrNoMeasurement, lastErr)
		}
		return nil, ErrNoMeasurement
	}
	age := clock().Sub(m.at)
	if age < 0 || age >= maxMeasurementAge {
		e.requestRefresh()
		if lastErr != nil {
			return nil, fmt.Errorf("%w: measured %s ago (last refresh failed: %v)", ErrNoMeasurement, age.Round(time.Second), lastErr)
		}
		return nil, fmt.Errorf("%w: measured %s ago", ErrNoMeasurement, age.Round(time.Second))
	}
	growth := e.Ledger.ReservedTotal() - m.base
	if growth < 0 {
		return nil, budget.ErrBlocked
	}
	if age >= refreshEvery || growth >= refreshGrowth {
		e.requestRefresh()
	}
	out := make(map[string]int64, len(m.components))
	for key, value := range m.components {
		out[key] = value
	}
	key := e.growthKey()
	if out[key] > int64(^uint64(0)>>1)-growth {
		return nil, budget.ErrBlocked
	}
	out[key] += growth
	return out, nil
}

func (e *Environment) requestRefresh() {
	e.measureMu.Lock()
	kick := e.kick
	e.measureMu.Unlock()
	if kick == nil {
		return
	}
	select {
	case kick <- struct{}{}:
	default:
	}
}

// refresh runs one measurement pass and publishes it. The baseline is taken
// before the pass, so anything reserved while it runs counts as growth (at
// worst twice, never zero times). A pass that ran out of time keeps the previous
// measurement (still bounded by maxMeasurementAge); any other failure drops it,
// so integrity and cap refusals stay immediate.
func (e *Environment) refresh(ctx context.Context) error {
	e.refreshing.Lock()
	defer e.refreshing.Unlock()
	base := e.Ledger.ReservedBase()
	started := clock()
	pctx, cancel := context.WithTimeout(ctx, inventoryTimeout)
	components, err := e.measure(pctx)
	cancel()
	e.measureMu.Lock()
	defer e.measureMu.Unlock()
	if err != nil {
		e.lastErr = err
		if !errors.Is(err, context.DeadlineExceeded) {
			e.last = nil
		}
		return err
	}
	e.last, e.lastErr = &measurement{components: components, base: base, at: started}, nil
	return nil
}

// ServeCached takes the backend inventory off every caller's path: one pass runs
// now, then a background loop refreshes it. Afterwards Sample (and so Usage and
// every ledger reservation) reuses the latest measurement plus the bytes reserved
// since, and refuses when none is fresh enough. The returned error is the first
// pass's; serving continues fail-closed and the loop keeps retrying.
func (e *Environment) ServeCached(logf func(string, ...any)) error {
	if !e.hasBackends() {
		return nil
	}
	e.measureMu.Lock()
	if e.serving {
		e.measureMu.Unlock()
		return nil
	}
	ctx, cancel := context.WithCancel(context.Background())
	e.serving, e.kick, e.stopLoop, e.loopDone, e.logf = true, make(chan struct{}, 1), cancel, make(chan struct{}), logf
	e.measureMu.Unlock()
	err := e.refreshLogged(ctx, nil)
	go e.refreshLoop(ctx, err)
	return err
}

func (e *Environment) refreshLogged(ctx context.Context, prev error) error {
	t := time.Now()
	err := e.refresh(ctx)
	if e.logf != nil && ctx.Err() == nil {
		if err != nil {
			e.logf("capacity measurement failed after %s: %v", time.Since(t).Round(time.Millisecond), err)
		} else if prev != nil {
			e.logf("capacity measurement recovered in %s", time.Since(t).Round(time.Millisecond))
		}
	}
	return err
}

func (e *Environment) refreshLoop(ctx context.Context, prev error) {
	defer close(e.loopDone)
	timer := time.NewTimer(refreshEvery)
	defer timer.Stop()
	for {
		select {
		case <-ctx.Done():
			return
		case <-timer.C:
		case <-e.kick:
		}
		prev = e.refreshLogged(ctx, prev)
		select { // requests made during the pass are answered by it
		case <-e.kick:
		default:
		}
		if !timer.Stop() {
			select {
			case <-timer.C:
			default:
			}
		}
		timer.Reset(refreshEvery)
	}
}

// DetachLedger transfers its lifetime to the enclosing control owner.
func (e *Environment) DetachLedger() *budget.Ledger { l := e.Ledger; e.detached = true; return l }
func (e *Environment) Close() {
	e.measureMu.Lock()
	stop, done := e.stopLoop, e.loopDone
	e.measureMu.Unlock()
	if stop != nil {
		stop()
		<-done
	}
	if e.Mongo != nil {
		e.Mongo.Close()
	}
	if e.Postgres != nil {
		e.Postgres.Close()
	}
	if e.Ledger != nil && !e.detached {
		e.Ledger.Close()
	}
}

// Usage exposes logical components to the existing admission/health interface.
// Pending archive debt is added by the shared ingest fence, not twice here.
func (e *Environment) Usage() (config.Usage, error) {
	sample, err := e.Sample()
	if err != nil {
		return config.Usage{}, err
	}
	state := e.Ledger.Snapshot()
	for key, value := range sample.Components {
		state.Components[key] = value
	}
	var live int64
	for key, value := range state.Components {
		if strings.HasSuffix(key, ":pending") {
			continue
		}
		if value < 0 || value > int64(^uint64(0)>>1)-live {
			return config.Usage{}, budget.ErrBlocked
		}
		live += value
	}
	local, err := meter.Measure(e.State, filepath.Join(e.State, "ingest", "wal"), 0)
	if err != nil {
		return config.Usage{}, err
	}
	return config.Usage{LiveBytes: live, WALBytes: local.WALBytes, FreeBytes: sample.Free}, nil
}
