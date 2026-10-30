package health

import (
	"testing"

	"aifactory.local/storage/internal/config"
)

func TestDeriveMode(t *testing.T) {
	c := config.Default()
	if m := Derive(c, false, false); m != ModeFileOnly {
		t.Fatalf("default must be file-only, got %s", m)
	}
	c.MongoEnabled = true
	if m := Derive(c, true, false); m != ModeMongo {
		t.Fatalf("mongo-only expected, got %s", m)
	}
	c.PostgresEnabled = true
	if m := Derive(c, true, true); m != ModeBoth {
		t.Fatalf("both expected, got %s", m)
	}
}

func TestBuildSurfacesBlocked(t *testing.T) {
	r := Build(config.Default(), false, false, true, "corrupt")
	if !r.RegistryBlocked || r.RegistryBlockReason != "corrupt" {
		t.Fatalf("blocked state not surfaced: %+v", r)
	}
	if r.Mode != ModeFileOnly {
		t.Fatalf("mode should be file-only when DBs disabled, got %s", r.Mode)
	}
	if r.MongoUp || r.PostgresUp {
		t.Fatalf("no real adapters in this slice: up flags must be false")
	}
}
