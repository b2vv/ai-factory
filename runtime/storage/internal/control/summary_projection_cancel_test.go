package control_test

import (
	"aifactory.local/storage/internal/archive"
	"aifactory.local/storage/internal/control"
	"aifactory.local/storage/internal/wal"
	"context"
	"errors"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"reflect"
	"strings"
	"testing"
	"time"
)

func TestProjectionCancellationRetainsOwnedIntentAcrossRestart(t *testing.T) {
	d, dir, op := summaryControl(t)
	plan := control.ArchiveProjection{Action: "rebuild", Desired: archive.IndexCheckpoint{Project: "p", SourceGeneration: "g", ProjectionGeneration: "first", PolicyRevision: "0"}}
	failedProof := errors.New("synthetic cleanup not yet verified")
	if err := d.WithArchiveTransaction(op, "p", func(tx *control.ArchiveTransaction) error {
		if err := tx.ReserveProjection(plan, 1024); err != nil {
			return err
		}
		before := d.Budget().Snapshot().Pending
		if err := tx.FinishCancelledProjection(plan, func() error { return nil }); err == nil {
			t.Fatal("unwitnessed cancellation released intent")
		}
		foreign := plan
		foreign.Desired.ProjectionGeneration = "other"
		beforeWAL, _, err := wal.Accepted(filepath.Join(dir, "wal"))
		if err != nil {
			t.Fatal(err)
		}
		if err := tx.BeginProjectionCancellation(foreign); err == nil {
			t.Fatal("foreign operation cancelled")
		}
		afterWAL, report, err := wal.Accepted(filepath.Join(dir, "wal"))
		if err != nil || report.IsBlocked() || len(afterWAL) != len(beforeWAL) {
			t.Fatal("same-length foreign cancellation poisoned WAL", err)
		}
		if err := tx.BeginProjectionCancellation(plan); err != nil {
			return err
		}
		if err := tx.BeginProjectionCancellation(plan); err != nil {
			return err
		}
		cancelled, err := tx.ProjectionCancellation(plan)
		if err != nil || !cancelled {
			t.Fatal("cancellation witness missing", cancelled, err)
		}
		if err := tx.ReserveProjection(plan, 1024); err == nil {
			t.Fatal("cancelled operation replayed as normal")
		}
		if err := tx.FinishProjection(plan, func() error { return nil }); err == nil {
			t.Fatal("normal finish bypassed cleanup")
		}
		if err := tx.FinishCancelledProjection(plan, func() error { return failedProof }); !errors.Is(err, failedProof) {
			t.Fatal(err)
		}
		if !reflect.DeepEqual(before, d.Budget().Snapshot().Pending) {
			t.Fatal("cancellation replaced or refunded original intent")
		}
		return nil
	}); err != nil {
		t.Fatal(err)
	}
	if err := d.Close(); err != nil {
		t.Fatal(err)
	}
	var err error
	d, err = control.Open(dir)
	if err != nil {
		t.Fatal(err)
	}
	defer d.Close()
	attachArchiveLedger(t, d, dir)
	if err = d.WithArchiveTransaction(op, "p", func(tx *control.ArchiveTransaction) error {
		saved, err := tx.RecoveryProjection()
		if err != nil || saved == nil || *saved != plan {
			t.Fatal("operation lost", saved, err)
		}
		cancelled, err := tx.ProjectionCancellation(plan)
		if err != nil || !cancelled {
			t.Fatal("witness lost across restart", cancelled, err)
		}
		if err := tx.FinishCancelledProjection(plan, nil); err == nil {
			t.Fatal("nil cleanup proof accepted")
		}
		if err := tx.FinishCancelledProjection(plan, func() error { return nil }); err != nil {
			return err
		}
		if len(d.Budget().Snapshot().Pending) != 0 {
			t.Fatal("verified cleanup retained intent")
		}
		next := plan
		next.Desired.ProjectionGeneration = "next"
		if err := tx.ReserveProjection(next, 1024); err != nil {
			return err
		}
		cancelled, err = tx.ProjectionCancellation(next)
		if err != nil || cancelled {
			t.Fatal("old witness cancelled new operation", cancelled, err)
		}
		return tx.FinishProjection(next, func() error { return nil })
	}); err != nil {
		t.Fatal(err)
	}
	state, _, err := d.ArchiveState("p")
	if err != nil || state.CommittedOrdinal != 0 || state.NextOrdinal != 1 {
		t.Fatal("derived cancellation changed source commitment", state, err)
	}
}

func TestPendingProjectionRevokeIsUnacknowledgedUntilRecoveryAndRetry(t *testing.T) {
	d, dir, op := summaryControl(t)
	if _, err := d.SetConsent(op, "p", "synthetic", "summary", true); err != nil {
		t.Fatal(err)
	}
	state, _, err := d.ArchiveState("p")
	if err != nil {
		t.Fatal(err)
	}
	plan := control.ArchiveProjection{Action: "rebuild", Desired: archive.IndexCheckpoint{Project: "p", SourceGeneration: "g", ProjectionGeneration: "pending", PolicyRevision: fmt.Sprint(state.PolicyRevision)}}
	if err = d.WithArchiveTransaction(op, "p", func(tx *control.ArchiveTransaction) error { return tx.ReserveProjection(plan, 1024) }); err != nil {
		t.Fatal(err)
	}
	if _, err = d.SetConsent(op, "p", "synthetic", "summary", false); !errors.Is(err, control.ErrCapacity) {
		t.Fatal("pending revoke was acknowledged", err)
	}
	if _, _, err = d.ArchiveState("p"); !errors.Is(err, control.ErrBlocked) {
		t.Fatal("failed revoke left current process serving", err)
	}
	if err = d.Close(); err != nil {
		t.Fatal(err)
	}
	d, err = control.Open(dir)
	if err != nil {
		t.Fatal(err)
	}
	// An unacknowledged in-memory reduction is not a retained revocation witness.
	if consent := d.Registry().ConsentEpoch("p", "synthetic", "summary"); !consent.Enabled || consent.Epoch != 1 {
		t.Fatal("unexpected durable policy", consent)
	}
	attachArchiveLedger(t, d, dir)
	if err = d.WithArchiveTransaction(op, "p", func(tx *control.ArchiveTransaction) error {
		return tx.FinishProjection(plan, func() error { return nil })
	}); err != nil {
		t.Fatal(err)
	}
	if _, err = d.SetConsent(op, "p", "synthetic", "summary", false); err != nil {
		t.Fatal("revoke retry after verified recovery", err)
	}
	if err = d.Close(); err != nil {
		t.Fatal(err)
	}
	d, err = control.Open(dir)
	if err != nil {
		t.Fatal(err)
	}
	defer d.Close()
	if consent := d.Registry().ConsentEpoch("p", "synthetic", "summary"); consent.Enabled || consent.Epoch != 2 || consent.RevokedThrough != 2 {
		t.Fatal("acknowledged revoke did not survive restart", consent)
	}
}

func TestProjectionCancellationWitnessRefusedByActualOldReader(t *testing.T) {
	old := os.Getenv("SUMMARY_OLD_OPERATOR")
	if old == "" {
		t.Skip("SUMMARY_OLD_OPERATOR absent: actual cancellation downgrade refusal NOT_TESTED")
	}
	d, dir, op := summaryControl(t)
	if err := d.Close(); err != nil {
		t.Fatal(err)
	}
	run := func() ([]byte, error) {
		ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
		defer cancel()
		cmd := exec.CommandContext(ctx, old, "-state", dir)
		cmd.Stdin = strings.NewReader(`{"Operation":"consent","Project":"p","Provider":"old-reader-probe","Capability":"capture","Enabled":false}`)
		out, err := cmd.CombinedOutput()
		if ctx.Err() != nil {
			t.Fatal("old reader timeout")
		}
		return out, err
	}
	out, err := run()
	if err != nil || !strings.Contains(string(out), `"status":"applied"`) {
		t.Fatal("old reader positive control", string(out), err)
	}
	d, err = control.Open(dir)
	if err != nil {
		t.Fatal(err)
	}
	attachArchiveLedger(t, d, dir)
	state, _, err := d.ArchiveState("p")
	if err != nil {
		t.Fatal(err)
	}
	plan := control.ArchiveProjection{Action: "rebuild", Desired: archive.IndexCheckpoint{Project: "p", SourceGeneration: "g", ProjectionGeneration: "cancelled", PolicyRevision: fmt.Sprint(state.PolicyRevision)}}
	if err = d.WithArchiveTransaction(op, "p", func(tx *control.ArchiveTransaction) error {
		if err := tx.ReserveProjection(plan, 1024); err != nil {
			return err
		}
		return tx.BeginProjectionCancellation(plan)
	}); err != nil {
		t.Fatal(err)
	}
	if err = d.Close(); err != nil {
		t.Fatal(err)
	}
	out, err = run()
	if err == nil || !strings.Contains(string(out), `unknown mutation kind "archive_summary_projection_cancel_v1"`) {
		t.Fatal("old reader accepted retained cancellation", string(out), err)
	}
	d, err = control.Open(dir)
	if err != nil {
		t.Fatal("compatible new reader refused witness", err)
	}
	defer d.Close()
	if state, _, err = d.ArchiveState("p"); err != nil || !state.ProjectionCancelled {
		t.Fatal("cancellation witness lost", state, err)
	}
}
