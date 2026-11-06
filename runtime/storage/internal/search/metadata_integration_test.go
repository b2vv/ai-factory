//go:build integration

package search

import (
	"aifactory.local/storage/internal/archive"
	"aifactory.local/storage/internal/budget"
	"aifactory.local/storage/internal/control"
	"aifactory.local/storage/internal/registry"
	"aifactory.local/storage/internal/workflow"
	"context"
	"fmt"
	"github.com/jackc/pgx/v5"
	"net/url"
	"os"
	"path/filepath"
	"testing"
	"time"
)

func metadataStore(t *testing.T) *Store {
	t.Helper()
	dsn := os.Getenv("PG_DSN")
	if dsn == "" {
		t.Skip("PG_DSN absent: metadata projection NOT_TESTED")
	}
	ctx := context.Background()
	admin, err := pgx.Connect(ctx, dsn)
	if err != nil {
		t.Fatal(err)
	}
	schema := fmt.Sprintf("metadata_search_%d", time.Now().UnixNano())
	if _, err := admin.Exec(ctx, "CREATE SCHEMA "+pgx.Identifier{schema}.Sanitize()); err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() {
		_, _ = admin.Exec(ctx, "DROP SCHEMA "+pgx.Identifier{schema}.Sanitize()+" CASCADE")
		_ = admin.Close(ctx)
	})
	u, err := url.Parse(dsn)
	if err != nil || u.Scheme == "" {
		t.Fatal("fixture requires PostgreSQL URL", err)
	}
	q := u.Query()
	q.Set("search_path", schema)
	u.RawQuery = q.Encode()
	w, err := workflow.OpenPostgres(ctx, u.String())
	if err != nil {
		t.Fatal(err)
	}
	if err := w.UpgradeArchiveMetadata(ctx); err != nil {
		t.Fatal(err)
	}
	w.Close()
	s, err := Open(ctx, u.String())
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(s.Close)
	return s
}
func TestMetadataProjectionCheckpointAndRebuild(t *testing.T) {
	s := metadataStore(t)
	c := Checkpoint{Project: "p", SourceGeneration: "source-g", ProjectionGeneration: "projection-a", PolicyRevision: "0"}
	if err := s.BeginRebuild(c, ""); err != nil {
		t.Fatal(err)
	}
	now := time.Date(2026, 11, 5, 12, 0, 0, 123456789, time.UTC)
	e := archive.Envelope{Version: 2, Record: archive.Record{Project: "p", SessionID: "s", MessageID: "m", Text: "authoritative terms"}, Metadata: archive.Metadata{Generation: "source-g", Ordinal: 1, CapturedAt: &now}}
	if err := s.PutEnvelope(e, c); err != nil {
		t.Fatal(err)
	}
	if err := s.PutEnvelope(e, c); err != nil {
		t.Fatal("ambiguous projection retry", err)
	}
	got, found, err := s.Checkpoint("p")
	if err != nil || !found || got.Ordinal != 1 || got.Complete {
		t.Fatal(got, found, err)
	}
	if err := s.BeginRebuild(c, ""); err != nil {
		t.Fatal("same generation retry", err)
	}
	got, _, err = s.Checkpoint("p")
	if err != nil || got.Ordinal != 1 {
		t.Fatal("retry reset progress", got, err)
	}
	if err := s.CompleteCheckpoint(got, 3); err != nil {
		t.Fatal(err)
	} // Source high-water3 survives a purged row; the bounded source scan proved exhausted.
	got, _, err = s.Checkpoint("p")
	if err != nil || !got.Complete || got.Ordinal != 3 {
		t.Fatal(got, err)
	}
	next := c
	next.ProjectionGeneration = "projection-b"
	next.PolicyRevision = "1"
	if err := s.BeginRebuild(next, "projection-a"); err != nil {
		t.Fatal(err)
	}
	if err := s.PutEnvelope(e, c); err == nil {
		t.Fatal("stale generation wrote")
	}
	got, _, err = s.Checkpoint("p")
	if err != nil || got.Complete || got.Ordinal != 0 || got.ProjectionGeneration != "projection-b" {
		t.Fatal(got, err)
	}
	refs, _, err := s.Window("p", "", "")
	if err != nil || len(refs) != 0 {
		t.Fatal("rebuild retained old rows", refs, err)
	}
	if err := s.Purge("p"); err != nil {
		t.Fatal(err)
	}
	if _, found, err := s.Checkpoint("p"); err != nil || found {
		t.Fatal("purge retained checkpoint", found, err)
	}
}

func TestMetadataProjectionChargesCheckpointAndRows(t *testing.T) {
	s := metadataStore(t)
	ctx := context.Background()
	meter, err := workflow.OpenPostgresForMaintenance(ctx, s.pool.Config().ConnConfig.ConnString())
	if err != nil {
		t.Fatal(err)
	}
	defer meter.Close()
	before, err := meter.LogicalBytes(ctx, 1<<30)
	if err != nil {
		t.Fatal(err)
	}
	c := Checkpoint{Project: "p", SourceGeneration: "g", ProjectionGeneration: "projection", PolicyRevision: "0"}
	if err := s.BeginRebuild(c, ""); err != nil {
		t.Fatal(err)
	}
	after, err := meter.LogicalBytes(ctx, 1<<30)
	if err != nil || after <= before {
		t.Fatal("checkpoint escaped billing", before, after, err)
	}
	if _, err := meter.LogicalBytes(ctx, before); err == nil {
		t.Fatal("checkpoint exceeded cap undetected")
	}
	now := time.Date(2026, 11, 5, 12, 0, 0, 123456789, time.UTC)
	e := archive.Envelope{Version: 2, Record: archive.Record{Project: "p", SessionID: "s", MessageID: "m", Text: "billing terms"}, Metadata: archive.Metadata{Generation: "g", Ordinal: 1, CapturedAt: &now, SourceEventTime: &now}}
	if err := s.PutEnvelope(e, c); err != nil {
		t.Fatal(err)
	}
	populated, err := meter.LogicalBytes(ctx, 1<<30)
	if err != nil || populated <= after {
		t.Fatal("metadata row escaped billing", populated, after, err)
	}
	legacyCost, err := s.ReservationBytes(e.Record)
	if err != nil {
		t.Fatal(err)
	}
	if populated-after <= legacyCost {
		t.Fatal("metadata indexes not charged", populated-after, legacyCost)
	}
	reserved, err := s.ProjectionReservationBytes(e, c)
	if err != nil || reserved < populated-after {
		t.Fatal("projection reservation insufficient", reserved, populated-after, err)
	}
}

func TestMetadataHiddenPageProgressIsIncompleteAndRetryable(t *testing.T) {
	s := metadataStore(t)
	c := Checkpoint{Project: "p", SourceGeneration: "s", ProjectionGeneration: "g", PolicyRevision: "0"}
	if err := s.BeginRebuild(c, ""); err != nil {
		t.Fatal(err)
	}
	if err := s.AdvanceCheckpoint(c, 100); err != nil {
		t.Fatal(err)
	}
	if err := s.AdvanceCheckpoint(c, 100); err != nil {
		t.Fatal("ambiguous retry", err)
	}
	next, found, err := s.Checkpoint("p")
	if err != nil || !found || next.Ordinal != 100 || next.Complete {
		t.Fatal(next, found, err)
	}
	if err := s.AdvanceCheckpoint(c, 101); err == nil {
		t.Fatal("stale progress accepted")
	}
	if err := s.CompleteCheckpoint(next, 150); err != nil {
		t.Fatal(err)
	}
	done, _, err := s.Checkpoint("p")
	if err != nil || !done.Complete || done.Ordinal != 150 {
		t.Fatal(done, err)
	}
	if err := s.AdvanceCheckpoint(next, 150); err == nil {
		t.Fatal("completed checkpoint mistaken for incomplete retry")
	}
}

func TestMetadataCoordinatorAdvancesHiddenPagesAndResetsPolicy(t *testing.T) {
	index := metadataStore(t)
	root := t.TempDir()
	d, err := control.Initialize(filepath.Join(root, "control"))
	if err != nil {
		t.Fatal(err)
	}
	defer d.Close()
	op := registry.Principal{Kind: registry.Operator}
	if err := d.MintProject(op, "p", "p"); err != nil {
		t.Fatal(err)
	}
	if err := d.BeginArchiveMigration(op, "p", "s"); err != nil {
		t.Fatal(err)
	}
	l, err := budget.Initialize(filepath.Join(root, "ledger"), budget.Policy{LiveCap: 1 << 30}, func() (budget.Sample, error) { return budget.LocalSample(root, 1<<30) })
	if err != nil {
		t.Fatal(err)
	}
	if err := d.AttachBudget(l); err != nil {
		t.Fatal(err)
	}
	source := archive.NewMemStore()
	if err := d.WithArchiveTransaction(op, "p", func(tx *control.ArchiveTransaction) error {
		for n := 1; n <= 151; n++ {
			r := archive.Record{Project: "p", SessionID: "s", MessageID: fmt.Sprint(n), Text: "needle"}
			e, err := tx.Reserve(r, nil, true)
			if err != nil {
				return err
			}
			if err := source.PutEnvelope(e); err != nil {
				return err
			}
			if err := tx.Complete(r, func(archive.Envelope) error { return nil }, func() error { return nil }); err != nil {
				return err
			}
		}
		return nil
	}); err != nil {
		t.Fatal(err)
	}
	run := func(gate func(archive.Record) bool) error {
		return d.WithArchiveTransaction(op, "p", func(tx *control.ArchiveTransaction) error {
			_, err := index.ProjectArchive(tx, source, gate)
			return err
		})
	}
	gate := func(r archive.Record) bool { return r.MessageID == "151" }
	if err := run(gate); err != nil {
		t.Fatal(err)
	}
	first, found, err := index.Checkpoint("p")
	if err != nil || !found || first.Ordinal != 100 || first.Complete {
		t.Fatal(first, found, err)
	}
	if err := run(gate); err != nil {
		t.Fatal(err)
	}
	done, _, err := index.Checkpoint("p")
	if err != nil || done.Ordinal != 151 || !done.Complete || done.ProjectionGeneration != first.ProjectionGeneration {
		t.Fatal(done, err)
	}
	refs, _, err := index.Window("p", "needle", "")
	if err != nil || len(refs) != 1 {
		t.Fatal(refs, err)
	}
	if _, err := d.SetConsent(op, "p", "synthetic", "capture", false); err != nil {
		t.Fatal(err)
	}
	if err := run(func(archive.Record) bool { return false }); err != nil {
		t.Fatal(err)
	}
	reset, _, err := index.Checkpoint("p")
	if err != nil || reset.Ordinal != 100 || reset.Complete || reset.ProjectionGeneration == first.ProjectionGeneration || reset.PolicyRevision == first.PolicyRevision {
		t.Fatal(reset, err)
	}
	refs, _, err = index.Window("p", "needle", "")
	if err != nil || len(refs) != 0 {
		t.Fatal("old policy index retained", refs, err)
	}
	// Crash after PG committed an incomplete progress operation but before ledger
	// release. Recovery must reuse its exact receipt, then continue past the page.
	final := reset
	final.Ordinal = 150
	plan := control.ArchiveProjection{Action: "advance", Expected: reset, Desired: final}
	if err := d.WithArchiveTransaction(op, "p", func(tx *control.ArchiveTransaction) error {
		cost, err := index.CheckpointReservationBytes(final)
		if err != nil {
			return err
		}
		if err := tx.ReserveProjection(plan, cost); err != nil {
			return err
		}
		return index.AdvanceCheckpoint(reset, 150)
	}); err != nil {
		t.Fatal(err)
	}
	if err := run(func(archive.Record) bool { return false }); err != nil {
		t.Fatal("resume skipped-page checkpoint", err)
	}
	recovered, _, err := index.Checkpoint("p")
	if err != nil || !recovered.Complete || recovered.Ordinal != 151 || recovered.ProjectionGeneration != reset.ProjectionGeneration {
		t.Fatal(recovered, err)
	}

	if len(l.Snapshot().Pending) != 0 {
		t.Fatal("index intent not released")
	}
}

func TestMetadataReadbackRejectsStaleDerivedColumns(t *testing.T) {
	s := metadataStore(t)
	for n, assignment := range []string{"captured_key=NULL", "source_time_key=NULL", "terms=to_tsvector('simple','wrong')", "project_hash='wrong'"} {
		project := fmt.Sprint(n)
		c := Checkpoint{Project: project, SourceGeneration: "s", ProjectionGeneration: "g", PolicyRevision: "0"}
		if err := s.BeginRebuild(c, ""); err != nil {
			t.Fatal(err)
		}
		now := time.Now().UTC()
		e := archive.Envelope{Version: 2, Record: archive.Record{Project: project, SessionID: "s", MessageID: "m", Text: "needle"}, Metadata: archive.Metadata{Generation: "s", Ordinal: 1, CapturedAt: &now, SourceEventTime: &now}}
		if err := s.PutEnvelope(e, c); err != nil {
			t.Fatal(err)
		}
		after := c
		after.Ordinal = 1
		if matches, err := s.MatchesEnvelope(e, after); err != nil || !matches {
			t.Fatal("positive proof", matches, err)
		}
		if _, err := s.pool.Exec(context.Background(), "UPDATE archive_index SET "+assignment+" WHERE project=$1", project); err != nil {
			t.Fatal(err)
		}
		if matches, err := s.MatchesEnvelope(e, after); err != nil || matches {
			t.Fatal("stale derived column accepted", assignment, matches, err)
		}
		if err := s.PutEnvelope(e, c); err == nil {
			t.Fatal("retry accepted stale column", assignment)
		}
	}
}
