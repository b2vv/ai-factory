// Package budgetenv binds the accounting ledger to production logical inventory.
// It does not own authority: callers must already hold the control state lock.
package budgetenv

import (
	"aifactory.local/storage/internal/meter"
	"context"
	"crypto/sha256"
	"encoding/hex"
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
}

// sampleMaxAge bounds how long an unchanged token may stand for an inventory; after
// it a refresh pass rereads only changed rows. fullCheckEvery bounds how long rows that
// were not reread go without the complete validating read.
const (
	sampleMaxAge   = 30 * time.Second
	fullCheckEvery = 10 * time.Minute
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
func (e *Environment) Sample() (budget.Sample, error) {
	s, err := budget.LocalSample(e.State, e.limit)
	if err != nil {
		return s, err
	}
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	e.cacheMu.Lock()
	defer e.cacheMu.Unlock()
	if e.Mongo != nil {
		token := fmt.Sprint(archive.WriteGeneration())
		n, err := e.mongoInv.get(token, func(prev *archive.Inventory) (*archive.Inventory, error) {
			return e.Mongo.Inventory(ctx, e.limit, prev)
		}, func(inv *archive.Inventory) int64 { return inv.Total })
		if err != nil {
			return s, err
		}
		s.Components[e.mongoKey] = n
		debt, err := ingest.PendingLogicalBytes(filepath.Join(e.State, "ingest", "wal"), e.walLimit, e.Mongo)
		if err != nil {
			return s, err
		}
		s.Components[e.mongoKey+":pending"] = debt
	}
	if e.Postgres != nil {
		token, err := e.Postgres.WALPosition(ctx)
		if err != nil {
			return s, err
		}
		n, err := e.pgInv.get(token, func(prev *workflow.Inventory) (*workflow.Inventory, error) {
			return e.Postgres.Inventory(ctx, e.limit, prev)
		}, func(inv *workflow.Inventory) int64 { return inv.Total })
		if err != nil {
			return s, err
		}
		s.Components[e.postgresKey] = n
	}
	return s, nil
}

// DetachLedger transfers its lifetime to the enclosing control owner.
func (e *Environment) DetachLedger() *budget.Ledger { l := e.Ledger; e.detached = true; return l }
func (e *Environment) Close() {
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
