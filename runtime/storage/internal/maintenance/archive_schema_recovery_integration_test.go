//go:build integration

package maintenance

import (
	"aifactory.local/storage/internal/archive"
	"aifactory.local/storage/internal/budget"
	"aifactory.local/storage/internal/budgetenv"
	"aifactory.local/storage/internal/config"
	"aifactory.local/storage/internal/control"
	"aifactory.local/storage/internal/registry"
	"aifactory.local/storage/internal/workflow"
	"context"
	"fmt"
	"github.com/jackc/pgx/v5"
	"go.mongodb.org/mongo-driver/mongo"
	"go.mongodb.org/mongo-driver/mongo/options"
	"os"
	"reflect"
	"testing"
	"time"
)

func TestArchiveSchemaIntentCrashRecovery(t *testing.T) {
	uri := os.Getenv("MONGO_URI")
	if uri == "" || os.Getenv("PG_DSN") == "" {
		t.Skip("isolated real databases required")
	}
	for _, phase := range []string{"before-ddl", "mongo-only", "both-ready", "source-intent", "index-intent", "schema-conflict", "without-pg", "schema-capacity"} {
		t.Run(phase, func(t *testing.T) {
			ctx := context.Background()
			dsn := isolatedDSN(t)
			db := fmt.Sprintf("schema_retry_%d", time.Now().UnixNano())
			client, e := mongo.Connect(ctx, options.Client().ApplyURI(uri))
			if e != nil {
				t.Fatal(e)
			}
			defer func() { client.Database(db).Drop(ctx); client.Disconnect(ctx) }()
			source, e := archive.OpenMongo(ctx, uri, db, "archive")
			if e != nil {
				t.Fatal(e)
			}
			defer source.Close()
			pg, e := workflow.OpenPostgres(ctx, dsn)
			if e != nil {
				t.Fatal(e)
			}
			defer pg.Close()
			cfg := config.Default()
			cfg.MongoEnabled = true
			cfg.MongoURI = uri
			cfg.MongoDB = db
			cfg.MongoCollection = "archive"
			cfg.PostgresEnabled = phase != "without-pg"
			cfg.PostgresDSN = dsn
			state := t.TempDir()
			d, e := control.InitializeBudgeted(state, cfg)
			if e != nil {
				t.Fatal(e)
			}
			op := registry.Principal{Kind: registry.Operator}
			if e = d.MintProject(op, "p", "fixture"); e != nil {
				t.Fatal(e)
			}
			if e = d.BeginArchiveMigration(op, "p", "g"); e != nil {
				t.Fatal(e)
			}
			env, e := budgetenv.Open(state, &cfg)
			if e != nil {
				t.Fatal(e)
			}
			if phase == "schema-capacity" {
				limited, e := budget.Initialize(state+"/limited-ledger", budget.Policy{LiveCap: budget.FileBytes + archive.SchemaLogicalBytes()}, func() (budget.Sample, error) {
					return budget.Sample{Free: 1 << 30}, nil
				})
				if e != nil {
					t.Fatal(e)
				}
				if e = d.AttachBudget(limited); e != nil {
					t.Fatal(e)
				}
				// Isolate shared-ledger admission from the separate local-directory meter.
				// Both actual databases remain private fixtures; no production limit changes.
				var requested int64
				d.SetCapacityCheck(func(cost int64) error { requested = cost; return nil })
				e = PrepareArchiveSchema(ctx, d, op, "p", source, pg)
				if requested != archive.SchemaLogicalBytes()+workflow.SchemaLogicalBytes() {
					t.Error("incomplete schema reservation", requested)
				}
				if e == nil {
					t.Errorf("PG schema liability omitted from reservation: %v", e)
				}
				ready, readErr := source.MetadataSchemaReady()
				if readErr != nil || ready || len(limited.Snapshot().Pending) != 0 {
					t.Fatal("DDL ran before complete schema admission", ready, readErr)
				}
				d.Close()
				env.Close()
				return
			}
			if e = d.AttachBudget(env.DetachLedger()); e != nil {
				t.Fatal(e)
			}
			migrationPG := pg
			if phase == "without-pg" {
				migrationPG = nil
			}
			evidence := budget.Evidence{Kind: "archive-schema-v2", KeyHash: migrationHash("p"), PayloadHash: migrationHash(fmt.Sprintf("metadata-v2:pg=%t", migrationPG != nil))}
			cost := archive.SchemaLogicalBytes()
			if migrationPG != nil {
				cost += workflow.SchemaLogicalBytes()
			}
			if phase == "source-intent" || phase == "index-intent" {
				if e = PrepareArchiveSchema(ctx, d, op, "p", source, migrationPG); e != nil {
					t.Fatal(e)
				}
				evidence = budget.Evidence{Kind: "archive-source-v2", KeyHash: "fixture", PayloadHash: "fixture"}
				if phase == "index-intent" {
					evidence.Kind = "archive-index-v2"
				}
			}
			if e = d.WithArchiveWriter(op, "p", func(*control.ArchiveTransaction) error { return d.ReserveIdentifiedExternal(evidence, cost) }); e != nil {
				t.Fatal(e)
			}
			if phase != "before-ddl" && phase != "without-pg" {
				if e = source.EnsureMetadataSchema(); e != nil {
					t.Fatal(e)
				}
			}
			if phase == "both-ready" || phase == "schema-conflict" {
				if e = pg.UpgradeArchiveMetadata(ctx); e != nil {
					t.Fatal(e)
				}
			}
			if phase == "schema-conflict" {
				conn, e := pgx.Connect(ctx, dsn)
				if e != nil {
					t.Fatal(e)
				}
				_, e = conn.Exec(ctx, "UPDATE derived_index_version SET version=99")
				conn.Close(ctx)
				if e != nil {
					t.Fatal(e)
				}
			}
			before := d.Budget().Snapshot().Pending
			d.Close()
			env.Close()
			d, e = control.Open(state)
			if e != nil {
				t.Fatal(e)
			}
			defer d.Close()
			// Open existing ledger directly: the synthetic conflicting schema is intentionally
			// unreadable to the global sampler; schema preparation itself must retain the intent.
			ledger, e := budget.Open(state+"/budget.bin", func() (budget.Sample, error) { return budget.LocalSample(state, 1<<30) })
			if e != nil {
				t.Fatal(e)
			}
			if e = d.AttachBudget(ledger); e != nil {
				t.Fatal(e)
			}
			e = PrepareArchiveSchema(ctx, d, op, "p", source, migrationPG)
			if phase == "schema-conflict" {
				if e == nil || !reflect.DeepEqual(before, d.Budget().Snapshot().Pending) {
					t.Fatal("conflicting schema cleared reservation", e)
				}
				return
			}
			if e != nil {
				t.Fatal(e)
			}
			if phase == "source-intent" || phase == "index-intent" {
				if !reflect.DeepEqual(before, d.Budget().Snapshot().Pending) {
					t.Fatal("schema stole unrelated intent")
				}
				return
			}
			mr, e := source.MetadataSchemaReady()
			if e != nil || !mr {
				t.Fatal("Mongo schema not ready", e)
			}
			pr, e := pg.ArchiveMetadataReady(ctx)
			if e != nil || pr != (phase != "without-pg") {
				t.Fatal("PG schema not ready", e)
			}
			if len(d.Budget().Snapshot().Pending) != 0 {
				t.Fatal("schema recovery left intent")
			}
			if e = PrepareArchiveSchema(ctx, d, op, "p", source, migrationPG); e != nil || len(d.Budget().Snapshot().Pending) != 0 {
				t.Fatal("schema retry not idempotent", e)
			}
		})
	}
}
