// Package health reports per-capability status and the active mode. An unavailable
// API cannot serve this; the CLI/operator helper surfaces Docker-absent status
// out-of-band (PLAN §9.1, non-blocking obligation).
package health

import "aifactory.local/storage/internal/config"

// Mode describes which capabilities are active.
type Mode string

const (
	ModeFileOnly Mode = "file-only"    // no DB, no capture
	ModeMongo    Mode = "mongo-only"   // archive + archive query, no PG
	ModePostgres Mode = "postgres-only"
	ModeBoth     Mode = "both"
)

// Status is the health snapshot.
type Status struct {
	Mode           Mode
	MongoUp        bool
	PostgresUp     bool
	CaptureEnabled bool
	WALDepth       int
	Gaps           int
}

// Derive computes the mode from config and live store availability.
func Derive(c config.Config, mongoUp, pgUp bool) Mode {
	switch {
	case c.MongoEnabled && c.PostgresEnabled:
		return ModeBoth
	case c.MongoEnabled:
		return ModeMongo
	case c.PostgresEnabled:
		return ModePostgres
	default:
		return ModeFileOnly
	}
}
