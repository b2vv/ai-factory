//go:build integration

package budgetenv

import (
	"context"
	"fmt"
	"os"
	"testing"
	"time"

	"aifactory.local/storage/internal/archive"
	"aifactory.local/storage/internal/budget"
	"aifactory.local/storage/internal/config"
	"aifactory.local/storage/internal/control"
	"aifactory.local/storage/internal/ingest"
	"aifactory.local/storage/internal/search"
	"aifactory.local/storage/internal/workflow"
	"path/filepath"
)

func TestLogicalLedgerRealBackendsAndOfflineRestart(t *testing.T) {
	uri, dsn := os.Getenv("MONGO_URI"), os.Getenv("PG_DSN")
	if uri == "" || dsn == "" {
		t.Skip("BLOCKED: real synthetic Mongo/PG endpoints required")
	}
	cfg := config.Default()
	cfg.MongoEnabled = true
	cfg.MongoURI = uri
	cfg.MongoDB = fmt.Sprintf("ledger_%d", time.Now().UnixNano())
	cfg.MongoCollection = "archive"
	cfg.PostgresEnabled = true
	cfg.PostgresDSN = dsn
	root := t.TempDir()
	ctl, e := control.Initialize(root)
	if e != nil {
		t.Fatal(e)
	}
	defer ctl.Close()
	if e = Initialize(root, cfg); e != nil {
		t.Fatal(e)
	}
	env, e := Open(root, &cfg)
	if e != nil {
		t.Fatal(e)
	}
	defer env.Close()
	if e = ctl.AttachBudget(env.DetachLedger()); e != nil {
		t.Fatal(e)
	}
	ctx := context.Background()
	pg, e := workflow.OpenPostgres(ctx, dsn)
	if e != nil {
		t.Fatal(e)
	}
	defer pg.Close()
	mongo, e := archive.OpenMongo(ctx, uri, cfg.MongoDB, cfg.MongoCollection)
	if e != nil {
		t.Fatal(e)
	}
	defer mongo.Close()
	ing, e := ingest.Open(filepath.Join(root, "ingest", "wal"), config.NewAccountant(cfg), mongo)
	if e != nil {
		t.Fatal(e)
	}
	defer ing.Close()
	if e = ing.SetBudget(ctl.Budget()); e != nil {
		t.Fatal(e)
	}
	r := archive.Record{Project: cfg.MongoDB, SessionID: "s", MessageID: "m", Text: "alpha alpha beta"}
	usage, e := env.Usage()
	if e != nil {
		t.Fatal(e)
	}
	if _, e = ing.Accept(archive.IdentityKey(r), r, usage); e != nil {
		t.Fatal(e)
	}
	if len(ctl.Budget().Snapshot().Pending) != 0 {
		t.Fatal("accepted write not reconciled")
	}
	if n, e := ing.Drain(); e != nil || n != 1 {
		t.Fatal(n, e)
	}
	n, e := mongo.LogicalBytes(ctx, cfg.LiveCapBytes)
	if e != nil || n != archive.SchemaLogicalBytes()+archive.ReservationBytes(r) {
		t.Fatal(n, e)
	}
	index, e := search.Open(ctx, dsn)
	if e != nil {
		t.Fatal(e)
	}
	defer index.Close()
	before, e := pg.LogicalBytes(ctx, cfg.LiveCapBytes)
	if e != nil {
		t.Fatal(e)
	}
	cost, e := index.ReservationBytes(r)
	if e != nil {
		t.Fatal(e)
	}
	if e = ctl.Budget().Reserve(budget.Evidence{Kind: "synthetic-index"}, cost); e != nil {
		t.Fatal(e)
	}
	if e = index.Put(r); e != nil {
		t.Fatal(e)
	}
	after, e := pg.LogicalBytes(ctx, cfg.LiveCapBytes)
	if e != nil || after-before != cost {
		t.Fatalf("index cost mismatch before=%d after=%d cost=%d err=%v", before, after, cost, e)
	}
	if e = ctl.Budget().Finish(); e != nil {
		t.Fatal(e)
	}
	// Explicit maintenance only. Automatic DrainOnce wiring remains unapplied.
	usage, e = env.Usage()
	if e != nil {
		t.Fatal(e)
	}
	if out, e := ing.ReclaimWithUsage(func(archive.Record) bool { return true }, usage); e != nil || out.Dropped != 1 {
		t.Fatal(out, e)
	}
	if receipt, e := ing.Accept(archive.IdentityKey(r), r, usage); e != nil || !receipt.Duplicate {
		t.Fatal(receipt, e)
	}
	saved := ctl.Budget().Snapshot()
	ing.Close()
	ctl.Close()
	env.Close()
	offline, e := OpenOffline(root, nil)
	if e != nil {
		t.Fatal(e)
	}
	defer offline.Close()
	for key, value := range saved.Components {
		if key == "local" || key == "managed-external" {
			continue
		}
		if offline.Ledger.Snapshot().Components[key] != value {
			t.Fatalf("offline refunded %s", key)
		}
	}
}
