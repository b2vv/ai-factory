package health

import "aifactory.local/storage/internal/config"

// Report is the JSON health view served by the API. It makes the active mode and the
// durable control-registry state observable (no invisible failover): a BLOCKED registry
// is surfaced explicitly rather than silently serving permissive defaults.
type Report struct {
	Mode                Mode   `json:"mode"`
	MongoEnabled        bool   `json:"mongo_enabled"`
	PostgresEnabled     bool   `json:"postgres_enabled"`
	CaptureEnabled      bool   `json:"capture_enabled"`
	RegistryBlocked     bool   `json:"registry_blocked"`
	RegistryBlockReason string `json:"registry_block_reason,omitempty"`
	// DBs disabled in this slice: the backends are present only as in-process fakes.
	MongoUp    bool `json:"mongo_up"`
	PostgresUp bool `json:"postgres_up"`
}

// Build derives the health report. mongoUp/pgUp are false in this slice (no real
// adapters); the mode still reflects the configured capability switches.
func Build(c config.Config, mongoUp, pgUp, registryBlocked bool, blockReason string) Report {
	return Report{
		Mode:                Derive(c, mongoUp, pgUp),
		MongoEnabled:        c.MongoEnabled,
		PostgresEnabled:     c.PostgresEnabled,
		CaptureEnabled:      c.CaptureEnabled,
		RegistryBlocked:     registryBlocked,
		RegistryBlockReason: blockReason,
		MongoUp:             mongoUp,
		PostgresUp:          pgUp,
	}
}
