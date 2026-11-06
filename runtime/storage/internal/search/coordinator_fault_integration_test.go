//go:build integration

package search

import (
	"aifactory.local/storage/internal/archive"
	"aifactory.local/storage/internal/budget"
	"aifactory.local/storage/internal/control"
	"aifactory.local/storage/internal/registry"
	"bytes"
	"context"
	"errors"
	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
	"path/filepath"
	"reflect"
	"strings"
	"sync/atomic"
	"testing"
)

type projectionQueryCancellation struct {
	prefix  string
	enabled atomic.Bool
	fired   atomic.Bool
}

func (f *projectionQueryCancellation) TraceQueryStart(ctx context.Context, _ *pgx.Conn, data pgx.TraceQueryStartData) context.Context {
	if f.enabled.Load() && strings.HasPrefix(data.SQL, f.prefix) && !strings.Contains(data.SQL, "FOR UPDATE") && f.fired.CompareAndSwap(false, true) {
		cancelled, cancel := context.WithCancel(ctx)
		cancel()
		return cancelled
	}
	return ctx
}
func (*projectionQueryCancellation) TraceQueryEnd(context.Context, *pgx.Conn, pgx.TraceQueryEndData) {
}

// Each case owns a distinct PG schema. Cancellation is injected only in this
// store's pool, after durable intent admission, at a specific write/proof boundary.
func TestProjectionProofFailureRetainsExactIntentAndRetries(t *testing.T) {
	for _, tc := range []struct{ name, action, prefix string }{
		{"checkpoint-readback", "rebuild", "SELECT " + checkpointColumns + " FROM archive_checkpoint"},
		{"rebuild-write", "rebuild", "INSERT INTO archive_checkpoint"},
		{"empty-proof", "rebuild", "SELECT NOT EXISTS(SELECT 1 FROM archive_index"},
		{"record-proof", "project", "SELECT EXISTS(SELECT 1 FROM archive_index"},
	} {
		t.Run(tc.name, func(t *testing.T) {
			index := metadataStore(t)
			root := t.TempDir()
			d, err := control.Initialize(filepath.Join(root, "control"))
			if err != nil {
				t.Fatal(err)
			}
			defer d.Close()
			op := registry.Principal{Kind: registry.Operator}
			if err = d.MintProject(op, "p", "fixture"); err != nil {
				t.Fatal(err)
			}
			if err = d.BeginArchiveMigration(op, "p", "source"); err != nil {
				t.Fatal(err)
			}
			ledger, err := budget.Initialize(filepath.Join(root, "ledger"), budget.Policy{LiveCap: 1 << 30}, func() (budget.Sample, error) { return budget.LocalSample(root, 1<<30) })
			if err != nil {
				t.Fatal(err)
			}
			if err = d.AttachBudget(ledger); err != nil {
				t.Fatal(err)
			}
			source := archive.NewMemStore()
			record := archive.Record{Project: "p", SourceInstance: "source", SessionID: "s", MessageID: "m", Text: "original"}
			var envelope archive.Envelope
			if err = d.WithArchiveTransaction(op, "p", func(tx *control.ArchiveTransaction) error {
				var err error
				envelope, err = tx.Reserve(record, nil, true)
				if err != nil {
					return err
				}
				if err = source.PutEnvelope(envelope); err != nil {
					return err
				}
				return tx.Complete(record, func(archive.Envelope) error { return nil }, func() error { return nil })
			}); err != nil {
				t.Fatal(err)
			}
			c := Checkpoint{Project: "p", SourceGeneration: "source", ProjectionGeneration: "projection", PolicyRevision: "0"}
			plan := control.ArchiveProjection{Action: "rebuild", Desired: c}
			if tc.action == "project" {
				if err = index.BeginRebuild(c, ""); err != nil {
					t.Fatal(err)
				}
				plan.Action = "project"
				plan.Expected = c
				plan.Desired.Ordinal = 1
				plan.Identity = archive.Record{Project: "p", SourceInstance: "source", SessionID: "s", MessageID: "m"}
				plan.EnvelopeHash, err = envelopeDigest(envelope)
				if err != nil {
					t.Fatal(err)
				}
			}
			if err = d.WithArchiveTransaction(op, "p", func(tx *control.ArchiveTransaction) error { return tx.ReserveProjection(plan, 4096) }); err != nil {
				t.Fatal(err)
			}
			admitted := ledger.Snapshot().Pending
			fault := &projectionQueryCancellation{prefix: tc.prefix}
			fault.enabled.Store(true)
			cfg := index.pool.Config()
			cfg.ConnConfig.Tracer = fault
			index.pool.Close()
			index.pool, err = pgxpool.NewWithConfig(context.Background(), cfg)
			if err != nil {
				t.Fatal(err)
			}
			err = d.WithArchiveTransaction(op, "p", func(tx *control.ArchiveTransaction) error {
				return index.applyProjection(tx, source, func(archive.Record) bool { return true }, plan, 4096)
			})
			if !fault.fired.Load() || !errors.Is(err, context.Canceled) {
				t.Error("readback/write failure lost its cause", fault.fired.Load(), err)
			}
			pending := ledger.Snapshot().Pending
			if len(pending) != 1 || !reflect.DeepEqual(pending, admitted) {
				t.Fatal("failed proof released intent", pending)
			}
			state, active, err := d.ArchiveState("p")
			if err != nil || !active || state.Projection == nil || *state.Projection != plan {
				t.Fatal("failed proof changed durable operation", state, err)
			}
			got, found, err := source.LookupEnvelope(record)
			if err != nil || !found || got.Record != envelope.Record || got.Metadata.Ordinal != envelope.Metadata.Ordinal {
				t.Fatal("derived failure changed source", got, err)
			}
			acceptedBytes, encodeErr := archive.EncodeEnvelope(envelope)
			if encodeErr != nil {
				t.Fatal(encodeErr)
			}
			sourceBytes, encodeErr := archive.EncodeEnvelope(got)
			if encodeErr != nil || !bytes.Equal(acceptedBytes, sourceBytes) {
				t.Fatal("derived failure changed complete source metadata", encodeErr)
			}
			fault.enabled.Store(false)
			if err = d.WithArchiveTransaction(op, "p", func(tx *control.ArchiveTransaction) error {
				return index.RecoverProjection(tx, source, func(archive.Record) bool { return true })
			}); err != nil {
				t.Fatal("exact operation retry", err)
			}
			gotCheckpoint, found, err := index.Checkpoint("p")
			if err != nil || !found || gotCheckpoint != plan.Desired || len(ledger.Snapshot().Pending) != 0 {
				t.Fatal("retry incomplete", gotCheckpoint, err)
			}
		})
	}
}

func TestProjectArchivePropagatesFinalCheckpointFailure(t *testing.T) {
	index := metadataStore(t)
	root := t.TempDir()
	d, err := control.Initialize(filepath.Join(root, "control"))
	if err != nil {
		t.Fatal(err)
	}
	defer d.Close()
	op := registry.Principal{Kind: registry.Operator}
	if err := d.MintProject(op, "p", "fixture"); err != nil {
		t.Fatal(err)
	}
	if err := d.BeginArchiveMigration(op, "p", "source"); err != nil {
		t.Fatal(err)
	}
	ledger, err := budget.Initialize(filepath.Join(root, "ledger"), budget.Policy{LiveCap: 1 << 30}, func() (budget.Sample, error) { return budget.LocalSample(root, 1<<30) })
	if err != nil {
		t.Fatal(err)
	}
	if err := d.AttachBudget(ledger); err != nil {
		t.Fatal(err)
	}
	source := archive.NewMemStore()
	record := archive.Record{Project: "p", SessionID: "s", MessageID: "m", Text: "preserve"}
	if err := d.WithArchiveTransaction(op, "p", func(tx *control.ArchiveTransaction) error {
		e, err := tx.Reserve(record, nil, true)
		if err != nil {
			return err
		}
		if err := source.PutEnvelope(e); err != nil {
			return err
		}
		return tx.Complete(record, func(archive.Envelope) error { return nil }, func() error { return nil })
	}); err != nil {
		t.Fatal(err)
	}
	checkpoint := Checkpoint{Project: "p", SourceGeneration: "source", ProjectionGeneration: "index", PolicyRevision: "0"}
	if err := index.BeginRebuild(checkpoint, ""); err != nil {
		t.Fatal(err)
	}
	fault := &projectionQueryCancellation{prefix: "UPDATE archive_checkpoint"}
	fault.enabled.Store(true)
	cfg := index.pool.Config()
	cfg.ConnConfig.Tracer = fault
	index.pool.Close()
	index.pool, err = pgxpool.NewWithConfig(context.Background(), cfg)
	if err != nil {
		t.Fatal(err)
	}
	gate := func(archive.Record) bool { return false }
	err = d.WithArchiveTransaction(op, "p", func(tx *control.ArchiveTransaction) error {
		_, err := index.ProjectArchive(tx, source, gate)
		return err
	})
	if !fault.fired.Load() || !errors.Is(err, context.Canceled) {
		t.Errorf("final checkpoint failure reported success: %v", err)
	}
	got, found, err := index.Checkpoint("p")
	if err != nil || !found || got != checkpoint {
		t.Fatal("failed checkpoint write advanced index", got, err)
	}
	state, _, err := d.ArchiveState("p")
	if err != nil || state.Projection == nil || state.Projection.Action != "complete" || len(ledger.Snapshot().Pending) != 1 {
		t.Fatal("failed final checkpoint lost recovery intent", err)
	}
	fault.enabled.Store(false)
	if err := d.WithArchiveTransaction(op, "p", func(tx *control.ArchiveTransaction) error { return index.RecoverProjection(tx, source, gate) }); err != nil {
		t.Fatal(err)
	}
	got, found, err = index.Checkpoint("p")
	if err != nil || !found || !got.Complete || got.Ordinal != 1 || len(ledger.Snapshot().Pending) != 0 {
		t.Fatal("checkpoint retry incomplete", got, err)
	}
	actual, found, err := source.LookupEnvelope(record)
	if err != nil || !found || actual.Record != record {
		t.Fatal("index retry altered authoritative source", err)
	}
}
