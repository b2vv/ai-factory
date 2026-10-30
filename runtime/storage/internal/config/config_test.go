package config

import (
	"os"
	"path/filepath"
	"testing"
)

func TestLoadDefaultsDisabledEverything(t *testing.T) {
	c, err := Load("", func(string) string { return "" })
	if err != nil {
		t.Fatalf("Load: %v", err)
	}
	if c.MongoEnabled || c.PostgresEnabled || c.CaptureEnabled {
		t.Fatalf("all capabilities must default OFF: %+v", c)
	}
	if c.WALBytes != DefaultWALBytes || c.LiveCapBytes != DefaultLiveCapBytes {
		t.Fatalf("D4 caps not applied by default")
	}
	if c.AutoMessageTTL || c.BackfillEnabled {
		t.Fatalf("D4: no auto TTL and no backfill")
	}
}

func TestEnvOverridesEnable(t *testing.T) {
	env := map[string]string{"STORAGE_POSTGRES_ENABLED": "1"}
	c, err := Load("", func(k string) string { return env[k] })
	if err != nil {
		t.Fatalf("Load: %v", err)
	}
	if !c.PostgresEnabled {
		t.Fatalf("env override did not enable postgres")
	}
	if c.MongoEnabled {
		t.Fatalf("mongo must stay disabled")
	}
}

func TestFileOverlayPartial(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "config.json")
	if err := os.WriteFile(path, []byte(`{"mongo_enabled": true, "wal_bytes": 1048576}`), 0o600); err != nil {
		t.Fatal(err)
	}
	c, err := Load(path, func(string) string { return "" })
	if err != nil {
		t.Fatalf("Load: %v", err)
	}
	if !c.MongoEnabled {
		t.Fatalf("file overlay did not enable mongo")
	}
	if c.WALBytes != 1048576 {
		t.Fatalf("file overlay WAL bytes not applied: %d", c.WALBytes)
	}
	if c.LiveCapBytes != DefaultLiveCapBytes {
		t.Fatalf("absent overlay field must keep default, got %d", c.LiveCapBytes)
	}
}

func TestMalformedFileIsError(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "config.json")
	if err := os.WriteFile(path, []byte(`{not json`), 0o600); err != nil {
		t.Fatal(err)
	}
	if _, err := Load(path, func(string) string { return "" }); err == nil {
		t.Fatalf("malformed config must be an error")
	}
}

func TestValidateRejectsProhibited(t *testing.T) {
	c := Default()
	c.AutoMessageTTL = true
	if err := c.Validate(); err == nil {
		t.Fatalf("auto message TTL must be rejected by D4")
	}
	c = Default()
	c.BackfillEnabled = true
	if err := c.Validate(); err == nil {
		t.Fatalf("backfill must be rejected by D4")
	}
}

func TestAdmitNeverEvicts(t *testing.T) {
	a := NewAccountant(Default())
	// At the WAL bound, intake is rejected (backpressure), not resolved by eviction.
	adm := a.Admit(Usage{WALBytes: DefaultWALBytes, LiveBytes: 0, FreeBytes: DefaultLiveCapBytes}, 1)
	if adm.Allowed {
		t.Fatalf("intake past the WAL bound must be rejected, not admitted")
	}
}
