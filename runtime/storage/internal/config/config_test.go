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
	env := map[string]string{
		"STORAGE_POSTGRES_ENABLED": "1",
		"STORAGE_POSTGRES_DSN":     "postgres://u:p@127.0.0.1:5432/db?sslmode=disable",
	}
	c, err := Load("", func(k string) string { return env[k] })
	if err != nil {
		t.Fatalf("Load: %v", err)
	}
	if !c.PostgresEnabled {
		t.Fatalf("env override did not enable postgres")
	}
	if c.PostgresDSN == "" {
		t.Fatalf("env DSN not applied")
	}
	if c.MongoEnabled {
		t.Fatalf("mongo must stay disabled")
	}
}

func TestFileOverlayPartial(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "config.json")
	if err := os.WriteFile(path, []byte(`{"mongo_enabled": true, "wal_bytes": 1048576, "mongo_uri": "mongodb://127.0.0.1:27017/", "mongo_db": "factory", "mongo_collection": "archive"}`), 0o600); err != nil {
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

func TestEnabledBackendRequiresConnection(t *testing.T) {
	c := Default()
	c.MongoEnabled = true // no URI/DB/collection
	if err := c.Validate(); err == nil {
		t.Fatalf("mongo enabled without connection settings must be rejected (fail-closed)")
	}
	c = Default()
	c.PostgresEnabled = true // no DSN
	if err := c.Validate(); err == nil {
		t.Fatalf("postgres enabled without a DSN must be rejected (fail-closed)")
	}
}

func TestCaptureRequiresMongo(t *testing.T) {
	c := Default()
	c.CaptureEnabled = true // but mongo disabled: nowhere durable to land history
	if err := c.Validate(); err == nil {
		t.Fatalf("capture enabled without the archive backend must be rejected")
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

func TestAdmissionOverflowAndMaintenancePeak(t *testing.T) {
	c := Default()
	c.WALBytes = 1000
	c.LiveCapBytes = 2000
	c.FreeHeadroom = 100
	a := NewAccountant(c)
	if a.Admit(Usage{WALBytes: 1<<63 - 1, LiveBytes: 1, FreeBytes: 1<<63 - 1}, 10).Allowed {
		t.Fatal("overflow admitted")
	}
	if a.Admit(Usage{WALBytes: 0, LiveBytes: -1, FreeBytes: 1000}, 1).Allowed {
		t.Fatal("negative usage admitted")
	}
	peak, e := a.MaintenancePeak(Usage{LiveBytes: 1800, FreeBytes: 250}, 500)
	if e != nil || peak != 650 {
		t.Fatal(peak, e)
	}
	if _, e = a.MaintenancePeak(Usage{LiveBytes: 2001, FreeBytes: 1000}, 500); e == nil {
		t.Fatal("over-cap maintenance admitted")
	}
}

func TestMaintenancePendingDebtUsesLiveAndFreeNotWAL(t *testing.T) {
	c := Default()
	c.WALBytes = 1000
	c.LiveCapBytes = 2000
	c.FreeHeadroom = 100
	a := NewAccountant(c)
	// 150 bytes of free headroom, of which 100 is already promised to archive.
	peak, e := a.MaintenancePeakWithPending(Usage{LiveBytes: 1800, FreeBytes: 250}, 500, 100)
	if e != nil || peak != 550 {
		t.Fatalf("pending debt reused for staging: %d %v", peak, e)
	}
	// When the WAL limit binds, pending DB liability must not lower the WAL cap.
	peak, e = a.MaintenancePeakWithPending(Usage{LiveBytes: 0, FreeBytes: 10000}, 500, 100)
	if e != nil || peak != 1000 {
		t.Fatalf("archive debt incorrectly charged to WAL: %d %v", peak, e)
	}
	if _, e = a.MaintenancePeakWithPending(Usage{LiveBytes: 1900, FreeBytes: 10000}, 500, 101); e == nil {
		t.Fatal("unfunded pending debt admitted")
	}
}
