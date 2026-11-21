//go:build integration

package search

import (
	"aifactory.local/storage/internal/archive"
	"aifactory.local/storage/internal/budget"
	"aifactory.local/storage/internal/control"
	"aifactory.local/storage/internal/registry"
	"context"
	"errors"
	"fmt"
	"github.com/jackc/pgx/v5/pgxpool"
	"os"
	"path/filepath"
	"reflect"
	"testing"
)

func TestProjectionMissingSourceCancelsScopedPGAndRecoversAfterProofFailure(t *testing.T) {
	testProjectionSourceInvalidation(t, false, "")
}
func TestProjectionChangedSourceCancelsScopedPGAndRecoversAfterProofFailure(t *testing.T) {
	testProjectionSourceInvalidation(t, true, "")
}
func TestProjectionCancellationDoesNotFinishWithRetainedRows(t *testing.T) {
	for _, table := range []string{"archive_index", "archive_checkpoint"} {
		t.Run(table, func(t *testing.T) { testProjectionSourceInvalidation(t, false, table) })
	}
}
func testProjectionSourceInvalidation(t *testing.T, changed bool, keepTable string) {
	index := metadataStore(t)
	root := t.TempDir()
	dir := filepath.Join(root, "control")
	d, err := control.Initialize(dir)
	if err != nil {
		t.Fatal(err)
	}
	defer func() { d.Close() }()
	op := registry.Principal{Kind: registry.Operator}
	if err = d.MintProject(op, "p", "fixture"); err != nil {
		t.Fatal(err)
	}
	if err = d.BeginArchiveMigration(op, "p", "source"); err != nil {
		t.Fatal(err)
	}
	attach := func() {
		t.Helper()
		ledgerPath := filepath.Join(root, "ledger")
		sample := func() (budget.Sample, error) { return budget.LocalSample(root, 1<<30) }
		var ledger *budget.Ledger
		if _, e := os.Stat(ledgerPath); os.IsNotExist(e) {
			ledger, err = budget.Initialize(ledgerPath, budget.Policy{LiveCap: 1 << 30}, sample)
		} else {
			ledger, err = budget.Open(ledgerPath, sample)
		}
		if err != nil {
			t.Fatal(err)
		}
		if err = d.AttachBudget(ledger); err != nil {
			t.Fatal(err)
		}
	}
	attach()
	source := archive.NewMemStore()
	r := archive.Record{Project: "p", Provider: "synthetic", SourceInstance: "i", SessionID: "s", MessageID: "m", Type: archive.TypeMessage, Role: "user", Text: "synthetic original", ConsentEpoch: 1}
	var envelope archive.Envelope
	if err = d.WithArchiveTransaction(op, "p", func(tx *control.ArchiveTransaction) error {
		envelope, err = tx.Reserve(r, nil, true)
		if err != nil {
			return err
		}
		if err = source.PutEnvelope(envelope); err != nil {
			return err
		}
		if err = tx.Complete(r, func(expected archive.Envelope) error {
			actual, found, e := source.LookupEnvelope(r)
			if e != nil {
				return e
			}
			if !found || !reflect.DeepEqual(actual, expected) {
				return archive.ErrIDConflict
			}
			return nil
		}, func() error { return nil }); err != nil {
			return err
		}
		return tx.FinishMigration(func(control.ArchiveState) error { return nil })
	}); err != nil {
		t.Fatal(err)
	}
	c := Checkpoint{Project: "p", SourceGeneration: "source", ProjectionGeneration: "pending", PolicyRevision: "0"}
	if err = index.BeginRebuild(c, ""); err != nil {
		t.Fatal(err)
	}
	preflightFailure := errors.New("synthetic ordinary projection proof read failure")
	err = d.WithArchiveTransaction(op, "p", func(tx *control.ArchiveTransaction) error {
		_, err := index.ProjectArchiveWithGate(tx, source, func(archive.Envelope) (bool, error) { return false, preflightFailure })
		return err
	})
	unchanged, found, readErr := index.Checkpoint("p")
	if !errors.Is(err, preflightFailure) || readErr != nil || !found || unchanged != c || len(d.Budget().Snapshot().Pending) != 0 {
		t.Fatal("transient proof failure advanced projection or reserved intent", err, readErr)
	}
	desired := c
	desired.Ordinal = 1
	digest, err := envelopeDigest(envelope)
	if err != nil {
		t.Fatal(err)
	}
	plan := control.ArchiveProjection{Action: "project", Expected: c, Desired: desired, Identity: archive.Record{Project: "p", SourceInstance: "i", SessionID: "s", MessageID: "m"}, EnvelopeHash: digest}
	cost, err := index.ProjectionReservationBytes(envelope, c)
	if err != nil {
		t.Fatal(err)
	}
	if err = d.WithArchiveTransaction(op, "p", func(tx *control.ArchiveTransaction) error { return tx.ReserveProjection(plan, cost) }); err != nil {
		t.Fatal(err)
	}
	// SQL commit succeeded; the operation's final control proof/Finish did not run.
	if err = index.PutEnvelope(envelope, c); err != nil {
		t.Fatal(err)
	}
	pending := d.Budget().Snapshot().Pending
	gateFailure := errors.New("synthetic derivation read unavailable")
	err = d.WithArchiveTransaction(op, "p", func(tx *control.ArchiveTransaction) error {
		return index.RecoverProjectionWithGate(tx, source, func(archive.Envelope) (bool, error) { return false, gateFailure })
	})
	if !errors.Is(err, gateFailure) || !reflect.DeepEqual(pending, d.Budget().Snapshot().Pending) {
		t.Fatal("transient gate failure changed intent", err)
	}
	source.SetAvailable(false)
	if err = d.WithArchiveTransaction(op, "p", func(tx *control.ArchiveTransaction) error {
		return index.RecoverProjection(tx, source, func(archive.Record) bool { return true })
	}); !errors.Is(err, archive.ErrUnavailable) {
		t.Fatal("temporary source outage changed meaning", err)
	}
	if !reflect.DeepEqual(pending, d.Budget().Snapshot().Pending) {
		t.Fatal("source outage released intent")
	}
	source.SetAvailable(true)
	if changed {
		source = archive.NewMemStore()
		updated := envelope
		updated.Record.Text = "changed authoritative source"
		if err = source.PutEnvelope(updated); err != nil {
			t.Fatal(err)
		}
	} else if _, err = source.Purge("p", "s"); err != nil {
		t.Fatal(err)
	}
	// Foreign project derived state must survive this project's scoped cleanup.
	foreign := Checkpoint{Project: "foreign", SourceGeneration: "source", ProjectionGeneration: "foreign", PolicyRevision: "0"}
	if err = index.BeginRebuild(foreign, ""); err != nil {
		t.Fatal(err)
	}
	f := envelope
	f.Record.Project = "foreign"
	if err = index.PutEnvelope(f, foreign); err != nil {
		t.Fatal(err)
	}
	foreign.Ordinal = 1
	if keepTable != "" {
		if keepTable != "archive_index" && keepTable != "archive_checkpoint" {
			t.Fatal("invalid fixed test table")
		}
		if _, err = index.pool.Exec(context.Background(), `CREATE OR REPLACE FUNCTION s1_keep_p_row() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN IF OLD.project='p' THEN RETURN NULL; END IF; RETURN OLD; END $$`); err != nil {
			t.Fatal(err)
		}
		if _, err = index.pool.Exec(context.Background(), fmt.Sprintf("CREATE TRIGGER s1_keep_row BEFORE DELETE ON %s FOR EACH ROW EXECUTE FUNCTION s1_keep_p_row()", keepTable)); err != nil {
			t.Fatal(err)
		}
		err = d.WithArchiveTransaction(op, "p", func(tx *control.ArchiveTransaction) error {
			return index.RecoverProjection(tx, source, func(archive.Record) bool { return true })
		})
		if !errors.Is(err, ErrCheckpoint) || !reflect.DeepEqual(pending, d.Budget().Snapshot().Pending) {
			t.Fatal("retained SQL row released owned intent", keepTable, err)
		}
		var remains bool
		if err = index.pool.QueryRow(context.Background(), fmt.Sprintf("SELECT EXISTS(SELECT 1 FROM %s WHERE project='p')", keepTable)).Scan(&remains); err != nil || !remains {
			t.Fatal("delete suppression did not retain row", keepTable, remains, err)
		}
		if _, err = index.pool.Exec(context.Background(), fmt.Sprintf("DROP TRIGGER s1_keep_row ON %s", keepTable)); err != nil {
			t.Fatal(err)
		}
		if _, err = index.pool.Exec(context.Background(), "DROP FUNCTION s1_keep_p_row()"); err != nil {
			t.Fatal(err)
		}
	}
	fault := &projectionQueryCancellation{prefix: "SELECT NOT EXISTS(SELECT 1 FROM archive_index"}
	fault.enabled.Store(true)
	cfg := index.pool.Config()
	cfg.ConnConfig.Tracer = fault
	index.pool.Close()
	index.pool, err = pgxpool.NewWithConfig(context.Background(), cfg)
	if err != nil {
		t.Fatal(err)
	}
	err = d.WithArchiveTransaction(op, "p", func(tx *control.ArchiveTransaction) error {
		return index.RecoverProjection(tx, source, func(archive.Record) bool { return true })
	})
	if !fault.fired.Load() || !errors.Is(err, context.Canceled) {
		t.Fatal("cleanup proof failure not reached", fault.fired.Load(), err)
	}
	if !reflect.DeepEqual(pending, d.Budget().Snapshot().Pending) {
		t.Fatal("failed cleanup proof refunded intent")
	}
	state, _, err := d.ArchiveState("p")
	if err != nil || !state.ProjectionCancelled {
		t.Fatal("cancellation not retained", state, err)
	}
	fault.enabled.Store(false)
	if _, found, err := index.Checkpoint("p"); err != nil || found {
		t.Fatal("SQL cleanup had not committed before readback failure", found, err)
	}
	if got, found, err := index.Checkpoint("foreign"); err != nil || !found || got != foreign {
		t.Fatal("cleanup crossed project", got, err)
	}
	foreignRows, _, foreignErr := index.Window("foreign", "synthetic", "")
	if foreignErr != nil || len(foreignRows) != 1 {
		t.Fatal("cleanup removed foreign project index rows", len(foreignRows), foreignErr)
	}
	if err = d.Close(); err != nil {
		t.Fatal(err)
	}
	d, err = control.Open(dir)
	if err != nil {
		t.Fatal(err)
	}
	attach()
	if err = d.WithArchiveTransaction(op, "p", func(tx *control.ArchiveTransaction) error {
		return index.RecoverProjection(tx, source, func(archive.Record) bool { return true })
	}); err != nil {
		t.Fatal("cancel recovery", err)
	}
	if len(d.Budget().Snapshot().Pending) != 0 {
		t.Fatal("verified cleanup retained intent")
	}
	if err = d.WithArchiveTransaction(op, "p", func(tx *control.ArchiveTransaction) error {
		_, err := index.ProjectArchive(tx, source, func(archive.Record) bool { return true })
		return err
	}); err != nil {
		t.Fatal("rebuild after cancellation", err)
	}
	got, found, err := index.Checkpoint("p")
	if err != nil || !found || !got.Complete || got.Ordinal != 1 || got.ProjectionGeneration == "pending" {
		t.Fatal("fresh projection did not rebuild", got, err)
	}
	if state, _, err = d.ArchiveState("p"); err != nil || state.CommittedOrdinal != 1 {
		t.Fatal("derived cleanup changed authoritative checkpoint", state, err)
	}
}
