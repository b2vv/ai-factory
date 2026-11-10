package control

import (
	"aifactory.local/storage/internal/archive"
	"aifactory.local/storage/internal/budget"
	"aifactory.local/storage/internal/config"
	"aifactory.local/storage/internal/wal"
	"encoding/json"
	"errors"
	"os"
	"path/filepath"
	"reflect"
	"testing"
)

func cancellationControl(t *testing.T) (*Durable, string, ArchiveProjection) {
	t.Helper()
	dir := t.TempDir()
	cfg := config.Default()
	cfg.FreeHeadroom = 0
	d, err := InitializeBudgeted(dir, cfg)
	if err != nil {
		t.Fatal(err)
	}
	if err = d.MintProject(operator(), "p", "fixture"); err != nil {
		t.Fatal(err)
	}
	if err = d.BeginArchiveMigration(operator(), "p", "g"); err != nil {
		t.Fatal(err)
	}
	attachCancellationLedger(t, d, dir)
	p := ArchiveProjection{Action: "rebuild", Desired: archive.IndexCheckpoint{Project: "p", SourceGeneration: "g", ProjectionGeneration: "pending", PolicyRevision: "0"}}
	return d, dir, p
}
func attachCancellationLedger(t *testing.T, d *Durable, dir string) {
	t.Helper()
	ledger, err := budget.Open(filepath.Join(dir, "budget.bin"), func() (budget.Sample, error) { return budget.LocalSample(dir, config.DefaultLiveCapBytes) })
	if err != nil {
		t.Fatal(err)
	}
	if err = d.AttachBudget(ledger); err != nil {
		t.Fatal(err)
	}
}

func TestProjectionCancellationAcceptedWALSurvivesMarkerFailure(t *testing.T) {
	d, dir, p := cancellationControl(t)
	if err := d.WithArchiveTransaction(operator(), "p", func(tx *ArchiveTransaction) error { return tx.ReserveProjection(p, 1024) }); err != nil {
		t.Fatal(err)
	}
	before := d.Budget().Snapshot().Pending
	staging := filepath.Join(dir, "control.meta.tmp")
	if err := os.Mkdir(staging, 0700); err != nil {
		t.Fatal(err)
	}
	err := d.WithArchiveTransaction(operator(), "p", func(tx *ArchiveTransaction) error { return tx.BeginProjectionCancellation(p) })
	if !errors.Is(err, ErrPersistence) {
		t.Fatal("marker failure acknowledged", err)
	}
	if blocked, _ := d.Blocked(); !blocked {
		t.Fatal("uncertain marker kept serving")
	}
	if !reflect.DeepEqual(before, d.Budget().Snapshot().Pending) {
		t.Fatal("marker failure replaced liability")
	}
	if err = os.Remove(staging); err != nil {
		t.Fatal(err)
	}
	if err = d.Close(); err != nil {
		t.Fatal(err)
	}
	d, err = Open(dir)
	if err != nil {
		t.Fatal(err)
	}
	defer d.Close()
	attachCancellationLedger(t, d, dir)
	if err = d.WithArchiveTransaction(operator(), "p", func(tx *ArchiveTransaction) error {
		yes, err := tx.ProjectionCancellation(p)
		if err != nil || !yes {
			t.Fatal("accepted cancellation lost", yes, err)
		}
		return tx.FinishCancelledProjection(p, func() error { return nil })
	}); err != nil {
		t.Fatal(err)
	}
	if len(d.Budget().Snapshot().Pending) != 0 {
		t.Fatal("compatible recovered proof failed to finish")
	}
}

func TestHistoricalProjectionWithoutCancellationProvisionRemainsHeld(t *testing.T) {
	d, dir, p := cancellationControl(t)
	// Arrange the old retained receipt shape (no cancellation-liability field),
	// with a conservative existing intent. This fixture is not a live upgrade.
	m := mutation{Kind: kArchiveProjection, Project: "p", ArchiveProjection: &p}
	raw, err := json.Marshal(m)
	if err != nil {
		t.Fatal(err)
	}
	if err = d.budget.Reserve(projectionEvidence(p), 1<<20); err != nil {
		t.Fatal(err)
	}
	receipt, err := d.w.Accept("historical-projection-fixture", raw)
	if err != nil {
		t.Fatal(err)
	}
	d.highWater = receipt.Seq
	if err = writeMeta(d.metaPath, metaFile{Initialized: true, HighWater: receipt.Seq}); err != nil {
		t.Fatal(err)
	}
	if err = d.Close(); err != nil {
		t.Fatal(err)
	}
	d, err = Open(dir)
	if err != nil {
		t.Fatal(err)
	}
	defer d.Close()
	attachCancellationLedger(t, d, dir)
	before := d.Budget().Snapshot().Pending
	records, _, err := wal.Accepted(filepath.Join(dir, "wal"))
	if err != nil {
		t.Fatal(err)
	}
	err = d.WithArchiveTransaction(operator(), "p", func(tx *ArchiveTransaction) error { return tx.BeginProjectionCancellation(p) })
	if !errors.Is(err, ErrCapacity) {
		t.Fatal("old reservation guessed to have cancellation capacity", err)
	}
	after, report, err := wal.Accepted(filepath.Join(dir, "wal"))
	if err != nil || report.IsBlocked() || len(after) != len(records) || !reflect.DeepEqual(before, d.Budget().Snapshot().Pending) {
		t.Fatal("refusal appended/refunded unknown liability", err)
	}
}

func TestHistoricalUnprovisionedCancellationReplayRefusesWitness(t *testing.T) {
	d, dir, p := cancellationControl(t)
	// Use the supported historical receipt shape seam: projection with omitted cost.
	m := mutation{Kind: kArchiveProjection, Project: "p", ArchiveProjection: &p}
	raw, err := json.Marshal(m)
	if err != nil {
		t.Fatal(err)
	}
	if err = d.budget.Reserve(projectionEvidence(p), 1<<20); err != nil {
		t.Fatal(err)
	}
	if _, err = d.w.Accept("historical-projection-replay", raw); err != nil {
		t.Fatal(err)
	}
	raw, err = json.Marshal(projectionCancellationMutation(p))
	if err != nil {
		t.Fatal(err)
	}
	receipt, err := d.w.Accept("historical-unprovisioned-cancel", raw)
	if err != nil {
		t.Fatal(err)
	}
	if err = writeMeta(d.metaPath, metaFile{Initialized: true, HighWater: receipt.Seq}); err != nil {
		t.Fatal(err)
	}
	if err = d.Close(); err != nil {
		t.Fatal(err)
	}
	reopened, err := Open(dir)
	if err != nil {
		if !errors.Is(err, ErrBlocked) {
			t.Fatal("unexpected replay refusal", err)
		}
		return
	}
	defer reopened.Close()
	if blocked, _ := reopened.Blocked(); !blocked {
		t.Fatal("unprovisioned cancellation replay became authority")
	}
}
