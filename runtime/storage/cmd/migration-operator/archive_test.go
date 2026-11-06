package main

import (
	"aifactory.local/storage/internal/search"
	"bytes"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestArchiveMigrationRequiresExplicitApplyAndWindow(t *testing.T) {
	for _, flags := range [][]string{{"-archive-metadata-v2"}, {"-archive-metadata-v2", "-apply"}, {"-archive-metadata-v2", "-exclusive-window"}} {
		state := filepath.Join(t.TempDir(), "absent")
		args := append(flags, "-state", state, "-project", "p", "-config", "missing")
		if err := run(args, &bytes.Buffer{}); err == nil {
			t.Fatal("implicit migration allowed")
		}
		if _, err := os.Stat(state); !os.IsNotExist(err) {
			t.Fatal("refused invocation touched state", err)
		}
	}
}

func TestArchiveMigrationModeRequiresPrivateConfig(t *testing.T) {
	state := filepath.Join(t.TempDir(), "absent")
	err := run([]string{"-archive-metadata-v2", "-apply", "-exclusive-window", "-state", state, "-project", "p", "-config", "missing"}, &bytes.Buffer{})
	if err == nil || !strings.Contains(err.Error(), "operator input unavailable") {
		t.Fatal("archive mode not recognized or config bypassed", err)
	}
	if _, err := os.Stat(state); !os.IsNotExist(err) {
		t.Fatal("invalid config touched state", err)
	}
}

func TestArchiveModeDoesNotEnableDeferredRollback(t *testing.T) {
	if err := run([]string{"-to", "0", "-ack-derived-data-removal", "-exclusive-window", "-state", "unused"}, &bytes.Buffer{}); err != errBackupDeferred {
		t.Fatal(err)
	}
	if err := run([]string{"-archive-metadata-v2=false", "-to", "0", "-ack-derived-data-removal", "-exclusive-window", "-state", "unused"}, &bytes.Buffer{}); err != errBackupDeferred {
		t.Fatal("false flag enabled rollback", err)
	}
}

func TestArchiveMigrationCannotOmitRequiredIndex(t *testing.T) {
	root := t.TempDir()
	state := filepath.Join(root, "state")
	if err := os.Mkdir(state, 0700); err != nil {
		t.Fatal(err)
	}
	if err := search.MarkRequired(state); err != nil {
		t.Fatal(err)
	}
	cfg := filepath.Join(root, "config.json")
	if err := os.WriteFile(cfg, []byte(`{"mongo_enabled":true,"mongo_uri":"mongodb://127.0.0.1:1","mongo_db":"synthetic","mongo_collection":"records"}`), 0600); err != nil {
		t.Fatal(err)
	}
	err := run([]string{"-archive-metadata-v2", "-apply", "-exclusive-window", "-state", state, "-project", "p", "-config", cfg}, &bytes.Buffer{})
	if err == nil || !strings.Contains(err.Error(), "required archive index") {
		t.Fatal("index requirement bypassed", err)
	}
	if _, err := os.Stat(filepath.Join(state, "wal")); !os.IsNotExist(err) {
		t.Fatal("required-index refusal touched control", err)
	}
}
