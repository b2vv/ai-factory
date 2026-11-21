//go:build integration

package api

import (
	"aifactory.local/storage/internal/archive"
	"aifactory.local/storage/internal/control"
	"aifactory.local/storage/internal/search"
	"aifactory.local/storage/internal/summary"
	"aifactory.local/storage/internal/workflow"
	"context"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"fmt"
	"github.com/jackc/pgx/v5"
	"net/url"
	"os"
	"reflect"
	"strconv"
	"testing"
	"time"
)

func clockProjectionStore(t *testing.T) *search.Store {
	t.Helper()
	dsn := os.Getenv("PG_DSN")
	if dsn == "" {
		t.Skip("PG_DSN absent: actual clock projection retention NOT_TESTED")
	}
	ctx := context.Background()
	admin, err := pgx.Connect(ctx, dsn)
	if err != nil {
		t.Fatal(err)
	}
	schema := fmt.Sprintf("summary_clock_%d", time.Now().UnixNano())
	if _, err = admin.Exec(ctx, "CREATE SCHEMA "+pgx.Identifier{schema}.Sanitize()); err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { admin.Exec(ctx, "DROP SCHEMA "+pgx.Identifier{schema}.Sanitize()+" CASCADE"); admin.Close(ctx) })
	uri, err := url.Parse(dsn)
	if err != nil {
		t.Fatal(err)
	}
	q := uri.Query()
	q.Set("search_path", schema)
	uri.RawQuery = q.Encode()
	pg, err := workflow.OpenPostgres(ctx, uri.String())
	if err != nil {
		t.Fatal(err)
	}
	if err = pg.UpgradeArchiveMetadata(ctx); err != nil {
		pg.Close()
		t.Fatal(err)
	}
	pg.Close()
	index, err := search.Open(ctx, uri.String())
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(index.Close)
	return index
}
func TestSummaryPendingProjectionClockRegressionRetainsIntentAndRows(t *testing.T) {
	index := clockProjectionStore(t)
	f := newSummaryClockFixture(t, false)
	f.server.SetSearchStore(index)
	state, _, err := f.control.ArchiveState("p")
	if err != nil {
		t.Fatal(err)
	}
	base := search.Checkpoint{Project: "p", SourceGeneration: "g", ProjectionGeneration: "clock-pending", PolicyRevision: strconv.FormatUint(state.PolicyRevision, 10)}
	if err = index.BeginRebuild(base, ""); err != nil {
		t.Fatal(err)
	}
	original, found, err := f.source.LookupEnvelope(archive.Record{Project: "p", SourceInstance: "i", SessionID: "s", MessageID: "source"})
	if err != nil || !found {
		t.Fatal(err)
	}
	// A completed SQL prefix precedes the owned summary operation.
	if err = index.PutEnvelope(original, base); err != nil {
		t.Fatal(err)
	}
	base.Ordinal = 1
	desired := base
	desired.Ordinal = 2
	raw, err := archive.EncodeEnvelope(f.envelope)
	if err != nil {
		t.Fatal(err)
	}
	hash := sha256.Sum256(raw)
	plan := control.ArchiveProjection{Action: "project", Expected: base, Desired: desired, Identity: archive.Record{Project: "p", SourceInstance: "i", SessionID: "s", MessageID: f.envelope.Record.MessageID}, EnvelopeHash: hex.EncodeToString(hash[:])}
	cost, err := index.ProjectionReservationBytes(f.envelope, base)
	if err != nil {
		t.Fatal(err)
	}
	if err = f.control.WithArchiveTransaction(f.op, "p", func(tx *control.ArchiveTransaction) error { return tx.ReserveProjection(plan, cost) }); err != nil {
		t.Fatal(err)
	}
	// SQL succeeded, but its final control Finish did not: this is a saved receipt.
	if err = index.PutEnvelope(f.envelope, base); err != nil {
		t.Fatal(err)
	}
	before, _, err := f.control.ArchiveState("p")
	if err != nil {
		t.Fatal(err)
	}
	pending := f.control.Budget().Snapshot().Pending
	rowsBefore, _, err := index.Window("p", "synthetic", "")
	if err != nil || len(rowsBefore) != 2 {
		t.Fatal("fixture rows", len(rowsBefore), err)
	}
	f.server.summaryProofClock = func() time.Time { return f.envelope.Metadata.CapturedAt.Add(-time.Hour) }
	err = f.server.RecoverIndex()
	after, _, stateErr := f.control.ArchiveState("p")
	checkpoint, present, cpErr := index.Checkpoint("p")
	rowsAfter, _, rowsErr := index.Window("p", "synthetic", "")
	if !errors.Is(err, summary.ErrVerifierClock) || stateErr != nil || cpErr != nil || rowsErr != nil || !present || checkpoint != desired || !reflect.DeepEqual(before, after) || !reflect.DeepEqual(pending, f.control.Budget().Snapshot().Pending) || !reflect.DeepEqual(rowsBefore, rowsAfter) || after.ProjectionCancelled {
		t.Fatal("clock uncertainty cancelled saved projection/rows", err, stateErr, cpErr, rowsErr)
	}
	f.server.summaryProofClock = nil
	if err = f.server.RecoverIndex(); err != nil {
		t.Fatal("corrected clock failed exact projection recovery", err)
	}
	checkpoint, present, err = index.Checkpoint("p")
	after, _, stateErr = f.control.ArchiveState("p")
	if err != nil || stateErr != nil || !present || checkpoint != desired || after.ProjectionCancelled || len(f.control.Budget().Snapshot().Pending) != 0 {
		t.Fatal("clock retry rebuilt/cancelled instead of finishing original receipt", err, stateErr)
	}
	rowsAfter, _, err = index.Window("p", "synthetic", "")
	if err != nil || !reflect.DeepEqual(rowsBefore, rowsAfter) {
		t.Fatal("clock retry changed SQL rows", err)
	}
	actual, found, err := f.source.LookupEnvelope(f.envelope.Record)
	actualRaw, _ := archive.EncodeEnvelope(actual)
	if err != nil || !found || string(raw) != string(actualRaw) {
		t.Fatal("projection clock recovery changed authoritative body", err)
	}
}
