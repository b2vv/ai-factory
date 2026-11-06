package main

import (
	"aifactory.local/storage/internal/config"
	"aifactory.local/storage/internal/control"
	"aifactory.local/storage/internal/registry"
	"context"
	"fmt"
	"net"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"sync/atomic"
	"testing"
	"time"
)

func TestProcessMetadataWitnessRequiresArchiveBeforeListen(t *testing.T) {
	root := t.TempDir()
	bin := buildFactory(t, root)
	state := filepath.Join(root, "state")
	d, err := control.InitializeBudgeted(state, config.Default())
	if err != nil {
		t.Fatal(err)
	}
	op := registry.Principal{Kind: registry.Operator}
	if err := d.MintProject(op, "p", "fixture"); err != nil {
		t.Fatal(err)
	}
	if err := d.BeginArchiveMigration(op, "p", "g"); err != nil {
		t.Fatal(err)
	}
	if err := d.Close(); err != nil {
		t.Fatal(err)
	}
	token := filepath.Join(root, "operator.json")
	writeFile0600(t, token, `{"id":"operator","secret":"smoke-secret"}`)
	ctx, cancel := context.WithTimeout(context.Background(), 3*time.Second)
	defer cancel()
	out, err := exec.CommandContext(ctx, bin, "-state", state, "-operator-token", token, "-listen", "127.0.0.1:0").CombinedOutput()
	if err == nil || ctx.Err() != nil || strings.Contains(string(out), "LISTEN ") || !strings.Contains(string(out), "archive metadata") {
		t.Fatalf("metadata witness served without source: %s (%v)", out, err)
	}
}

func TestProcessBlockedAuthorityPreservesMissingIntake(t *testing.T) {
	root := t.TempDir()
	bin := buildFactory(t, root)
	state := filepath.Join(root, "state")
	d, err := control.InitializeBudgeted(state, config.Default())
	if err != nil {
		t.Fatal(err)
	}
	op := registry.Principal{Kind: registry.Operator}
	if err := d.MintProject(op, "p", "fixture"); err != nil {
		t.Fatal(err)
	}
	if err := d.BeginArchiveMigration(op, "p", "g"); err != nil {
		t.Fatal(err)
	}
	if err := d.Close(); err != nil {
		t.Fatal(err)
	}
	marker := filepath.Join(state, "control.meta")
	saved, err := os.ReadFile(marker)
	if err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(marker, []byte("damaged"), 0600); err != nil {
		t.Fatal(err)
	}
	token := filepath.Join(root, "operator.json")
	writeFile0600(t, token, `{"id":"operator","secret":"smoke-secret"}`)
	cfg := filepath.Join(root, "config.json")
	// A private listener records attempted backend access without impersonating Mongo.
	// Refusal must precede any connection; a killed child alone is not this proof.
	backend, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatal(err)
	}
	defer backend.Close()
	var connections atomic.Int32
	go func() {
		for {
			c, err := backend.Accept()
			if err != nil {
				return
			}
			connections.Add(1)
			c.Close()
		}
	}()
	writeFile0600(t, cfg, fmt.Sprintf(`{"mongo_enabled":true,"mongo_uri":"mongodb://%s","mongo_db":"synthetic","mongo_collection":"records"}`, backend.Addr().String()))
	for attempt := 0; attempt < 2; attempt++ {
		ctx, cancel := context.WithTimeout(context.Background(), 3*time.Second)
		out, err := exec.CommandContext(ctx, bin, "-state", state, "-config", cfg, "-operator-token", token, "-listen", "127.0.0.1:0").CombinedOutput()
		if connections.Load() != 0 {
			cancel()
			t.Fatal("backend contacted before authority/migration readiness", connections.Load())
		}
		expired := ctx.Err()
		cancel()
		want := "archive startup refused while control authority is blocked"
		if attempt == 1 {
			want = "archive metadata migration incomplete"
		}
		if err == nil || expired != nil || strings.Contains(string(out), "LISTEN ") || !strings.Contains(string(out), want) {
			t.Fatalf("unsafe recovery startup: %s (%v)", out, err)
		}
		if _, err := os.Stat(filepath.Join(state, "ingest")); !os.IsNotExist(err) {
			t.Fatal("missing intake recreated", err)
		}
		if err := os.WriteFile(marker, saved, 0600); err != nil {
			t.Fatal(err)
		}
	}
}
