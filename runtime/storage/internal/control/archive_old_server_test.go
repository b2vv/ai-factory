package control_test

import (
	"aifactory.local/storage/internal/config"
	"aifactory.local/storage/internal/control"
	"aifactory.local/storage/internal/registry"
	"bufio"
	"context"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

// The exact baseline binary is supplied by the isolated compatibility fixture.
// Its absence is NOT proof of old-server refusal.
func TestOldServerRefusesArchiveWitness(t *testing.T) {
	old := os.Getenv("ARCHIVE_OLD_SERVER")
	if old == "" {
		t.Skip("ARCHIVE_OLD_SERVER absent: actual old-server compatibility NOT_TESTED")
	}
	root := t.TempDir()
	dir := filepath.Join(root, "state")
	token := filepath.Join(root, "operator.json")
	if err := os.WriteFile(token, []byte(`{"id":"op","secret":"synthetic-only"}`), 0600); err != nil {
		t.Fatal(err)
	}
	d, err := control.InitializeBudgeted(dir, config.Default())
	if err != nil {
		t.Fatal(err)
	}
	op := registry.Principal{ID: "op", Kind: registry.Operator}
	if err := d.MintProject(op, "p", "fixture"); err != nil {
		t.Fatal(err)
	}
	if err := d.Close(); err != nil {
		t.Fatal(err)
	}
	args := []string{"-state", dir, "-operator-token", token, "-listen", "127.0.0.1:0"}
	// Positive control: this same binary serves the unupgraded state.
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	cmd := exec.CommandContext(ctx, old, args...)
	stdout, err := cmd.StdoutPipe()
	if err != nil {
		t.Fatal(err)
	}
	if err := cmd.Start(); err != nil {
		t.Fatal(err)
	}
	scan := bufio.NewScanner(stdout)
	ready := scan.Scan() && strings.HasPrefix(scan.Text(), "LISTEN ")
	cancel()
	_ = cmd.Wait()
	if !ready {
		t.Fatal("baseline server failed positive startup control")
	}
	d, err = control.Open(dir)
	if err != nil {
		t.Fatal(err)
	}
	if err := d.BeginArchiveMigration(op, "p", "g"); err != nil {
		t.Fatal(err)
	}
	if err := d.Close(); err != nil {
		t.Fatal(err)
	}
	ctx, cancel = context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	out, err := exec.CommandContext(ctx, old, args...).CombinedOutput()
	if err == nil || ctx.Err() != nil || !strings.Contains(string(out), `unknown mutation kind "archive_metadata_v2_begin"`) || strings.Contains(string(out), "LISTEN ") {
		t.Fatalf("old server did not refuse witness before serving: %s (%v)", out, err)
	}
	// No ingestion records exist: refusal does not depend on a surviving G frame.
	if _, err := os.Stat(filepath.Join(dir, "ingest", "journal.wal")); err == nil {
		t.Fatal("unexpected intake fixture")
	}
}
