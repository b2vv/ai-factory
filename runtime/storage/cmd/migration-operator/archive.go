package main

import (
	"aifactory.local/storage/internal/archive"
	"aifactory.local/storage/internal/budget"
	"aifactory.local/storage/internal/budgetenv"
	"aifactory.local/storage/internal/config"
	"aifactory.local/storage/internal/control"
	"aifactory.local/storage/internal/ingest"
	"aifactory.local/storage/internal/maintenance"
	"aifactory.local/storage/internal/registry"
	"aifactory.local/storage/internal/search"
	"aifactory.local/storage/internal/workflow"
	"context"
	"crypto/rand"
	"crypto/sha256"
	"encoding/hex"
	"fmt"
	"io"
	"path/filepath"
	"strconv"
)

func archiveHash(s string) string { h := sha256.Sum256([]byte(s)); return hex.EncodeToString(h[:]) }
func runArchiveMigration(state, project, path string, out io.Writer) error {
	f, err := privateFile(path, 1<<20)
	if err != nil {
		return err
	}
	f.Close()
	cfg, err := config.Load(path, func(string) string { return "" })
	if err != nil {
		return fmt.Errorf("invalid explicit migration configuration")
	}
	if !cfg.MongoEnabled {
		return fmt.Errorf("archive migration requires authoritative Mongo")
	}
	required, err := search.Required(state)
	if err != nil {
		return err
	}
	if required && !cfg.PostgresEnabled {
		return fmt.Errorf("required archive index must be enabled for metadata migration")
	}
	ctx := context.Background()
	d, err := control.Open(state)
	if err != nil {
		return err
	}
	defer d.Close()
	if blocked, _ := d.Blocked(); blocked {
		return control.ErrBlocked
	}
	op := registry.Principal{Kind: registry.Operator}
	if !d.Registry().HasProject(project) {
		return registry.ErrUnknownProj
	}
	env, err := budgetenv.Open(state, &cfg)
	if err != nil {
		return err
	}
	defer env.Close()
	if err := d.AttachBudget(env.DetachLedger()); err != nil {
		return err
	}
	source, err := archive.OpenMongo(ctx, cfg.MongoURI, cfg.MongoDB, cfg.MongoCollection)
	if err != nil {
		return fmt.Errorf("archive migration backend unavailable")
	}
	defer source.Close()
	intake, err := ingest.OpenExisting(filepath.Join(state, "ingest", "wal"), config.NewAccountant(cfg), source)
	if err != nil {
		return fmt.Errorf("archive migration requires intact existing intake: %w", err)
	}
	defer intake.Close()
	if err := intake.SetBudget(d.Budget()); err != nil {
		return err
	}
	gate := func(r archive.Record) bool { return len(d.Retention().Serve([]archive.Record{r}, "capture")) == 1 }
	current, active, err := d.ArchiveState(project)
	if err != nil {
		return err
	}
	if !active {
		if err := d.WithStableAuthority(op, func(*registry.Registry) error { _, err := intake.DrainGated(gate); return err }); err != nil {
			return err
		}
		token := make([]byte, 32)
		if _, err := rand.Read(token); err != nil {
			return err
		}
		if err := d.BeginArchiveMigration(op, project, hex.EncodeToString(token)); err != nil {
			return err
		}
	}
	var pg *workflow.PGStore
	if cfg.PostgresEnabled {
		pg, err = workflow.OpenPostgres(ctx, cfg.PostgresDSN)
		if err != nil {
			return fmt.Errorf("migration index backend unavailable")
		}
		defer pg.Close()
	}
	if err := maintenance.PrepareArchiveSchema(ctx, d, op, project, source, pg); err != nil {
		return err
	}
	// Release only a proven pre-control-receipt crash; persisted source operations
	// are instead reconciled by the source transaction or migration below.
	pending := d.Budget().Snapshot().Pending
	if len(pending) == 1 && pending[0].Evidence.Kind == "archive-source-v2" {
		owned := false
		if err := d.WithArchiveTransaction(op, project, func(tx *control.ArchiveTransaction) error {
			operation, _, err := tx.RecoveryOperation()
			owned = operation != nil
			return err
		}); err != nil {
			return err
		}
		if !owned {
			if err := d.RecoverUnreservedArchiveIntent(op); err != nil {
				return err
			}
		}
	}
	if current.MigrationComplete {
		if err := d.WithArchiveTransaction(op, project, func(tx *control.ArchiveTransaction) error { return intake.RecoverEnvelope(tx, gate) }); err != nil {
			return err
		}
	} else {
		if err := d.WithArchiveTransaction(op, project, func(tx *control.ArchiveTransaction) error { return maintenance.MigrateArchiveSource(ctx, tx, source) }); err != nil {
			return err
		}
	}
	var index *search.Store
	if cfg.PostgresEnabled {
		index, err = search.Open(ctx, cfg.PostgresDSN)
		if err != nil {
			return err
		}
		defer index.Close()
		if err := d.WithArchiveTransaction(op, project, func(tx *control.ArchiveTransaction) error { return index.RecoverProjection(tx, source, gate) }); err != nil {
			return err
		}
		pending = d.Budget().Snapshot().Pending
		if len(pending) == 1 && pending[0].Evidence.Kind == "archive-index-v2" {
			if err := d.RecoverUnreservedArchiveIntent(op); err != nil {
				return err
			}
		}
		if err := ensureMigrationIndexMarker(d, op, state, project); err != nil {
			return err
		}
		for {
			complete := false
			if err := d.WithArchiveTransaction(op, project, func(tx *control.ArchiveTransaction) error {
				if _, err := index.ProjectArchive(tx, source, gate); err != nil {
					return err
				}
				c, found, err := index.Checkpoint(project)
				complete = found && c.Complete
				return err
			}); err != nil {
				return err
			}
			if complete {
				break
			}
		}
	}
	if err := d.WithArchiveTransaction(op, project, func(tx *control.ArchiveTransaction) error {
		return tx.FinishMigration(func(s control.ArchiveState) error {
			if index == nil {
				return nil
			}
			c, found, err := index.Checkpoint(project)
			if err != nil {
				return err
			}
			if !found || !c.Complete || c.SourceGeneration != s.Generation || c.PolicyRevision != strconv.FormatUint(s.PolicyRevision, 10) || c.Ordinal != s.CommittedOrdinal {
				return search.ErrCheckpoint
			}
			return nil
		})
	}); err != nil {
		return err
	}
	_, err = fmt.Fprintln(out, "ARCHIVE_METADATA_V2_READY")
	return err
}
func ensureMigrationIndexMarker(d *control.Durable, op registry.Principal, state, project string) error {
	evidence := budget.Evidence{Kind: "archive-index-capability", KeyHash: archiveHash("archive-index-required"), PayloadHash: archiveHash("derived-archive-index-v1")}
	return d.WithArchiveWriter(op, project, func(*control.ArchiveTransaction) error {
		ready, err := search.Required(state)
		if err != nil {
			return err
		}
		pending := d.Budget().Snapshot().Pending
		if ready {
			if len(pending) == 1 && pending[0].Evidence == evidence {
				if err := d.ReserveIdentifiedExternal(evidence, 0); err != nil {
					return err
				}
				return d.FinishExternal()
			}
			return nil
		}
		if err := search.MarkRequiredBudgeted(state, func(cost int64) error { return d.ReserveIdentifiedExternal(evidence, cost) }); err != nil {
			return err
		}
		return d.FinishExternal()
	})
}
