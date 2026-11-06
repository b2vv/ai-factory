//go:build integration

package maintenance

import (
	"aifactory.local/storage/internal/archive"
	"aifactory.local/storage/internal/budget"
	"aifactory.local/storage/internal/budgetenv"
	"aifactory.local/storage/internal/config"
	"aifactory.local/storage/internal/control"
	"aifactory.local/storage/internal/ingest"
	"aifactory.local/storage/internal/registry"
	"aifactory.local/storage/internal/search"
	"aifactory.local/storage/internal/workflow"
	"context"
	"encoding/json"
	"fmt"
	"go.mongodb.org/mongo-driver/mongo"
	"go.mongodb.org/mongo-driver/mongo/options"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

func TestArchiveMigrationPreservesRealMongoAndIndexesWithMeasuredLedger(t *testing.T) {
	uri := os.Getenv("MONGO_URI")
	if uri == "" {
		t.Skip("MONGO_URI absent: migration NOT_TESTED")
	}
	ctx := context.Background()
	dsn := isolatedDSN(t)
	db := fmt.Sprintf("archive_migration_%d", time.Now().UnixNano())
	admin, err := mongo.Connect(ctx, options.Client().ApplyURI(uri))
	if err != nil {
		t.Fatal(err)
	}
	defer func() { admin.Database(db).Drop(ctx); admin.Disconnect(ctx) }()
	source, err := archive.OpenMongo(ctx, uri, db, "archive")
	if err != nil {
		t.Fatal(err)
	}
	defer source.Close()
	pg, err := workflow.OpenPostgres(ctx, dsn)
	if err != nil {
		t.Fatal(err)
	}
	defer pg.Close()
	root := t.TempDir()
	cfg := config.Default()
	cfg.MongoEnabled = true
	cfg.MongoURI = uri
	cfg.MongoDB = db
	cfg.MongoCollection = "archive"
	cfg.PostgresEnabled = true
	cfg.PostgresDSN = dsn
	d, err := control.InitializeBudgeted(root, cfg)
	if err != nil {
		t.Fatal(err)
	}
	defer d.Close()
	op := registry.Principal{Kind: registry.Operator}
	if err := d.MintProject(op, "p", "p"); err != nil {
		t.Fatal(err)
	}
	if _, err := d.SetConsent(op, "p", "synthetic", "capture", true); err != nil {
		t.Fatal(err)
	}
	record := archive.Record{Project: "p", Provider: "synthetic", SourceInstance: "old", SessionID: "s", MessageID: "m", Text: "original needle", ConsentEpoch: 1}
	if err := source.Put(record); err != nil {
		t.Fatal(err)
	}
	env, err := budgetenv.Open(root, &cfg)
	if err != nil {
		t.Fatal(err)
	}
	defer env.Close()
	if err := d.AttachBudget(env.DetachLedger()); err != nil {
		t.Fatal(err)
	}
	if err := d.BeginArchiveMigration(op, "p", "g"); err != nil {
		t.Fatal(err)
	}
	for retry := 0; retry < 2; retry++ {
		if err := PrepareArchiveSchema(ctx, d, op, "p", source, pg); err != nil {
			t.Fatal(err)
		}
	}
	index, err := search.Open(ctx, dsn)
	if err != nil {
		t.Fatal(err)
	}
	defer index.Close()
	if err := d.WithArchiveTransaction(op, "p", func(tx *control.ArchiveTransaction) error {
		if err := MigrateArchiveSource(ctx, tx, source); err != nil {
			return err
		}
		if _, err := index.ProjectArchive(tx, source, func(r archive.Record) bool { return len(d.Retention().Serve([]archive.Record{r}, "capture")) == 1 }); err != nil {
			return err
		}
		return tx.FinishMigration(func(state control.ArchiveState) error {
			c, found, err := index.Checkpoint("p")
			if err != nil {
				return err
			}
			if !found || !c.Complete || c.Ordinal != state.CommittedOrdinal {
				return search.ErrCheckpoint
			}
			return nil
		})
	}); err != nil {
		t.Fatal(err)
	}
	got, found, err := source.LookupEnvelope(record)
	if err != nil || !found || got.Record != record || !got.Metadata.Legacy || got.Metadata.CapturedAt != nil || got.Metadata.SourceEventTime != nil {
		t.Fatal(got, found, err)
	}
	refs, _, err := index.Window("p", "needle", "")
	if err != nil || len(refs) != 1 || refs[0].PayloadHash != search.RecordHash(record) {
		t.Fatal(refs, err)
	}
	if len(d.Budget().Snapshot().Pending) != 0 {
		t.Fatal("pending ledger after migration")
	}
	if _, err := env.Sample(); err != nil {
		t.Fatal("measured upgraded representation", err)
	}
}

func TestArchiveOperatorMigratesLegacyIntakeAndRetries(t *testing.T) {
	testArchiveOperatorMigration(t, "legacy")
}
func TestArchiveOperatorRecoversInterruptedMigration(t *testing.T) {
	for _, mode := range []string{"orphan-source", "owned-source", "orphan-index", "mongo-only", "multi-page", "checkpoint-read-error"} {
		t.Run(mode, func(t *testing.T) { testArchiveOperatorMigration(t, mode) })
	}
}
func testArchiveOperatorMigration(t *testing.T, mode string) {
	uri := os.Getenv("MONGO_URI")
	if uri == "" {
		t.Skip("MONGO_URI absent: operator migration NOT_TESTED")
	}
	ctx := context.Background()
	dsn := isolatedDSN(t)
	db := fmt.Sprintf("archive_operator_%d", time.Now().UnixNano())
	admin, err := mongo.Connect(ctx, options.Client().ApplyURI(uri))
	if err != nil {
		t.Fatal(err)
	}
	defer func() { admin.Database(db).Drop(ctx); admin.Disconnect(ctx) }()
	source, err := archive.OpenMongo(ctx, uri, db, "archive")
	if err != nil {
		t.Fatal(err)
	}
	defer source.Close()
	pg, err := workflow.OpenPostgres(ctx, dsn)
	if err != nil {
		t.Fatal(err)
	}
	defer pg.Close()
	root := t.TempDir()
	state := filepath.Join(root, "state")
	cfg := config.Default()
	cfg.MongoEnabled = true
	cfg.MongoURI = uri
	cfg.MongoDB = db
	cfg.MongoCollection = "archive"
	cfg.PostgresEnabled = mode != "mongo-only"
	cfg.PostgresDSN = dsn
	d, err := control.InitializeBudgeted(state, cfg)
	if err != nil {
		t.Fatal(err)
	}
	op := registry.Principal{Kind: registry.Operator}
	if err := d.MintProject(op, "p", "p"); err != nil {
		t.Fatal(err)
	}
	if _, err := d.SetConsent(op, "p", "synthetic", "capture", true); err != nil {
		t.Fatal(err)
	}
	if err := d.Close(); err != nil {
		t.Fatal(err)
	}
	intake, err := ingest.Open(filepath.Join(state, "ingest", "wal"), config.NewAccountant(cfg), source)
	if err != nil {
		t.Fatal(err)
	}
	record := archive.Record{Project: "p", Provider: "synthetic", SourceInstance: "legacy", SessionID: "s", MessageID: "m", Text: "original needle", ConsentEpoch: 1}
	if _, err := intake.Accept(archive.IdentityKey(record), record, config.Usage{FreeBytes: 1 << 40}); err != nil {
		t.Fatal(err)
	}
	if mode == "orphan-source" || mode == "owned-source" || mode == "orphan-index" || mode == "checkpoint-read-error" {
		if _, err := intake.Drain(); err != nil {
			t.Fatal(err)
		}
	}
	if err := intake.Close(); err != nil {
		t.Fatal(err)
	}
	expectedCount := int64(1)
	if mode == "multi-page" {
		for n := 0; n < 100; n++ {
			extra := record
			extra.MessageID = fmt.Sprintf("extra-%03d", n)
			if err := source.Put(extra); err != nil {
				t.Fatal(err)
			}
		}
		expectedCount = 101
	}
	if mode == "orphan-source" || mode == "owned-source" || mode == "orphan-index" || mode == "checkpoint-read-error" {
		recovery, err := control.Open(state)
		if err != nil {
			t.Fatal(err)
		}
		recoveryEnv, err := budgetenv.Open(state, &cfg)
		if err != nil {
			t.Fatal(err)
		}
		if err := recovery.AttachBudget(recoveryEnv.DetachLedger()); err != nil {
			t.Fatal(err)
		}
		if err := recovery.BeginArchiveMigration(op, "p", "fixture-generation"); err != nil {
			t.Fatal(err)
		}
		if err := PrepareArchiveSchema(ctx, recovery, op, "p", source, pg); err != nil {
			t.Fatal(err)
		}
		switch mode {
		case "checkpoint-read-error":
			index, err := search.Open(ctx, dsn)
			if err != nil {
				t.Fatal(err)
			}
			err = recovery.WithArchiveTransaction(op, "p", func(tx *control.ArchiveTransaction) error {
				if err := MigrateArchiveSource(ctx, tx, source); err != nil {
					return err
				}
				_, err := index.ProjectArchive(tx, source, func(archive.Record) bool { return true })
				return err
			})
			index.Close()
			if err != nil {
				t.Fatal(err)
			}
		case "owned-source":
			if err := recovery.WithArchiveTransaction(op, "p", func(tx *control.ArchiveTransaction) error { _, err := tx.Reserve(record, nil, true); return err }); err != nil {
				t.Fatal(err)
			}
		case "orphan-index":
			if err := recovery.WithArchiveTransaction(op, "p", func(tx *control.ArchiveTransaction) error {
				if err := MigrateArchiveSource(ctx, tx, source); err != nil {
					return err
				}
				return tx.FinishMigration(func(control.ArchiveState) error { return nil })
			}); err != nil {
				t.Fatal(err)
			}
			if err := recovery.Budget().Reserve(budget.Evidence{Kind: "archive-index-v2", KeyHash: "fixture-orphan", PayloadHash: "fixture-orphan"}, 4096); err != nil {
				t.Fatal(err)
			}
		default:
			if err := recovery.Budget().Reserve(budget.Evidence{Kind: "archive-source-v2", KeyHash: "fixture-orphan", PayloadHash: "fixture-orphan"}, 4096); err != nil {
				t.Fatal(err)
			}
		}
		if err := recovery.Close(); err != nil {
			t.Fatal(err)
		}
		recoveryEnv.Close()
	}
	path := filepath.Join(root, "config.json")
	raw, err := json.Marshal(map[string]any{"mongo_enabled": true, "mongo_uri": uri, "mongo_db": db, "mongo_collection": "archive", "postgres_enabled": cfg.PostgresEnabled, "postgres_dsn": dsn})
	if err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(path, raw, 0600); err != nil {
		t.Fatal(err)
	}
	bin := filepath.Join(root, "migration-operator")
	build := exec.Command("go", "build", "-o", bin, "../../cmd/migration-operator")
	if out, err := build.CombinedOutput(); err != nil {
		t.Fatalf("build: %s (%v)", out, err)
	}
	for retry := 0; retry < 2; retry++ {
		if mode == "checkpoint-read-error" && retry == 1 {
			if err := os.WriteFile(path, raw, 0600); err != nil {
				t.Fatal(err)
			}
		}
		var faultFired interface{ Load() bool }
		if mode == "checkpoint-read-error" && retry == 0 {
			proxyDSN, fired := checkpointFailureProxy(t, dsn)
			faultFired = fired
			var document map[string]any
			if err := json.Unmarshal(raw, &document); err != nil {
				t.Fatal(err)
			}
			document["postgres_dsn"] = proxyDSN
			proxyRaw, err := json.Marshal(document)
			if err != nil {
				t.Fatal(err)
			}
			if err := os.WriteFile(path, proxyRaw, 0600); err != nil {
				t.Fatal(err)
			}
		}

		commandContext, cancel := context.WithTimeout(ctx, 30*time.Second)
		out, err := exec.CommandContext(commandContext, bin, "-archive-metadata-v2", "-apply", "-exclusive-window", "-state", state, "-project", "p", "-config", path).CombinedOutput()
		deadlineErr := commandContext.Err()
		cancel()
		if deadlineErr != nil {
			t.Fatal("migration did not terminate within its fixture bound", deadlineErr)
		}
		if faultFired != nil {
			if !faultFired.Load() || err == nil || !strings.Contains(string(out), "fixture-checkpoint-read-failure") || strings.Contains(string(out), "ARCHIVE_METADATA_V2_READY") {
				t.Fatalf("final proof error lost: fired=%v error=%v output=%s", faultFired.Load(), err, out)
			}
			continue
		}
		if err != nil || strings.TrimSpace(string(out)) != "ARCHIVE_METADATA_V2_READY" {
			t.Fatalf("operator failed: %s (%v)", out, err)
		}
	}
	got, found, err := source.LookupEnvelope(record)
	if err != nil || !found || got.Record != record || !got.Metadata.Legacy || got.Metadata.CapturedAt != nil || got.Metadata.Ordinal <= 0 {
		t.Fatal(got, found, err)
	}
	if cfg.PostgresEnabled {
		index, err := search.Open(ctx, dsn)
		if err != nil {
			t.Fatal(err)
		}
		defer index.Close()
		checkpoint, found, err := index.Checkpoint("p")
		if err != nil || !found || !checkpoint.Complete || checkpoint.Ordinal != expectedCount {
			t.Fatal(checkpoint, found, err)
		}
	}
	d, err = control.Open(state)
	if err != nil {
		t.Fatal(err)
	}
	defer d.Close()
	status, active, err := d.ArchiveState("p")
	if err != nil || !active || !status.MigrationComplete || status.CommittedOrdinal != expectedCount || status.NextOrdinal != expectedCount+1 {
		t.Fatal(status, active, err)
	}
	records, err := source.Fetch("p")
	if err != nil || int64(len(records)) != expectedCount {
		t.Fatal("source cardinality changed", len(records), err)
	}
	if mode == "mongo-only" {
		required, err := search.Required(state)
		if err != nil || required {
			t.Fatal("source-only migration enabled PG", required, err)
		}
	}
}
