package health

import "aifactory.local/storage/internal/config"

// Report is the JSON health view served by the API. It makes the active mode and the
// durable control-registry state observable (no invisible failover): a BLOCKED registry
// is surfaced explicitly rather than silently serving permissive defaults.
type Report struct {
	SessionExtracts     *SessionExtracts `json:"session_extracts,omitempty"`
	Index               *Index           `json:"index,omitempty"`
	Mode                Mode             `json:"mode"`
	MongoEnabled        bool             `json:"mongo_enabled"`
	PostgresEnabled     bool             `json:"postgres_enabled"`
	CaptureEnabled      bool             `json:"capture_enabled"`
	RegistryBlocked     bool             `json:"registry_blocked"`
	RegistryBlockReason string           `json:"registry_block_reason,omitempty"`
	// DBs disabled in this slice: the backends are present only as in-process fakes.
	MongoUp    bool `json:"mongo_up"`
	PostgresUp bool `json:"postgres_up"`
	// Ingestion backlog/recovery view (F5): present when capture is enabled and an ingestor is
	// wired. nil otherwise. The API layer fills this from the ingestor's Progress().
	Ingestion *Ingestion `json:"ingestion,omitempty"`
}

// Ingestion is the drain backlog + recovery view (F5): depth (not yet processed; processed includes quarantine),
// lag (how far the committed watermark trails the newest durable sequence), and gaps (ambiguous/
// damaged regions preserved by a BLOCKED recovery). It is a plain mirror of ingest.Progress so
// the health package takes no dependency on the ingest package.
type Ingestion struct {
	Accepted       int    `json:"accepted"`
	Processed      int    `json:"processed"`
	Depth          int    `json:"depth"`
	HighestSeq     uint64 `json:"highest_seq"`
	CommittedSeq   uint64 `json:"committed_seq"`
	LagSeq         uint64 `json:"lag_seq"`
	Blocked        bool   `json:"blocked"`
	BlockedRegions int    `json:"blocked_regions"`
	WALBytes       int64  `json:"wal_bytes"`
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

type Index struct {
	Enabled         bool `json:"enabled"`
	LastCycleFailed bool `json:"last_cycle_failed"`
}

// SessionExtracts reports component configuration and the last bounded cycle,
// never per-session freshness, backlog completion or native-capture completeness.
type SessionExtracts struct {
	Enabled             bool   `json:"enabled"`
	LastCycleFailed     bool   `json:"last_cycle_failed"`
	Kind                string `json:"kind"`
	CaptureCompleteness string `json:"capture_completeness"`
}
