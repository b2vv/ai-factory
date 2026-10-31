// Package config holds the pilot defaults (owner decision D4) and the capacity
// accounting used to enforce bounded storage WITHOUT evicting accepted records.
package config

import "fmt"

// Pilot defaults from D4. All are configurable; these are starting limits to
// validate under synthetic load, not measured production sizing.
const (
	DefaultWALBytes         int64 = 256 * 1024 * 1024       // 256 MiB write-ahead log
	DefaultLiveCapBytes     int64 = 10 * 1024 * 1024 * 1024 // 10 GiB live data (incl. DB/index/control/dedup metadata)
	DefaultWarnFraction           = 0.80                    // warn at 80% of live cap
	DefaultFreeHeadroom     int64 = 1 * 1024 * 1024 * 1024  // keep 1 GiB filesystem free
	DefaultBackupMaxAgeDays       = 30                      // backups expire after 30 days
	DefaultBackupBudget     int64 = 20 * 1024 * 1024 * 1024 // 20 GiB backup budget (separately accounted)
)

// Config is the effective runtime configuration. Modules are disabled by default.
type Config struct {
	// Capability switches — all OFF by default (owner must enable each).
	MongoEnabled    bool
	PostgresEnabled bool
	CaptureEnabled  bool // conversation capture; off by default and gated further by consent

	// Connection settings for the real backends. Required (non-empty) only when the
	// corresponding capability is enabled; never defaulted to a live endpoint.
	MongoURI        string // e.g. mongodb://host:port/
	MongoDB         string // database name for the archive
	MongoCollection string // collection name for archived records
	PostgresDSN     string // e.g. postgres://user:pass@host:port/db?sslmode=disable

	// D4 capacity/privacy.
	WALBytes         int64
	LiveCapBytes     int64
	WarnFraction     float64
	FreeHeadroom     int64
	BackupMaxAgeDays int
	BackupBudget     int64

	AutoMessageTTL  bool // D4: no automatic message-age TTL -> false
	BackfillEnabled bool // D4: historical backfill disabled -> false
	HookGapOnly     bool // D4: gap-only hooks, no client transcript spool -> true
}

// Default returns the owner-approved pilot defaults with every capability disabled.
func Default() Config {
	return Config{
		MongoEnabled:     false,
		PostgresEnabled:  false,
		CaptureEnabled:   false,
		WALBytes:         DefaultWALBytes,
		LiveCapBytes:     DefaultLiveCapBytes,
		WarnFraction:     DefaultWarnFraction,
		FreeHeadroom:     DefaultFreeHeadroom,
		BackupMaxAgeDays: DefaultBackupMaxAgeDays,
		BackupBudget:     DefaultBackupBudget,
		AutoMessageTTL:   false,
		BackfillEnabled:  false,
		HookGapOnly:      true,
	}
}

// Validate rejects a nonsensical configuration.
func (c Config) Validate() error {
	if c.WALBytes <= 0 || c.LiveCapBytes <= 0 {
		return fmt.Errorf("config: WAL and live cap must be positive")
	}
	if c.WarnFraction <= 0 || c.WarnFraction > 1 {
		return fmt.Errorf("config: warn fraction must be in (0,1]")
	}
	if c.AutoMessageTTL {
		return fmt.Errorf("config: automatic message-age TTL is prohibited by D4")
	}
	if c.BackfillEnabled {
		return fmt.Errorf("config: historical backfill is disabled by D4")
	}
	// Enabled backends require explicit connection settings; they are never defaulted to a
	// live endpoint (fail-closed: an enabled-but-unconfigured backend must not start).
	if c.MongoEnabled && (c.MongoURI == "" || c.MongoDB == "" || c.MongoCollection == "") {
		return fmt.Errorf("config: mongo enabled but MongoURI/MongoDB/MongoCollection not all set")
	}
	if c.PostgresEnabled && c.PostgresDSN == "" {
		return fmt.Errorf("config: postgres enabled but PostgresDSN not set")
	}
	// Capture requires the archive (Mongo) backend to be ENABLED: per the accepted delivery
	// sequence the Mongo module precedes capture adapters (PLAN §11.1), and archive-committed
	// (a durable Mongo write) is the required terminal for a captured record (PLAN §6.4). This
	// is a config-time check on the ENABLED flag only; it does NOT concern runtime
	// availability. A temporarily-UNAVAILABLE-but-enabled Mongo is allowed and is handled at
	// runtime by the agreed WAL buffering/backpressure (accepted records wait in the bounded
	// WAL and drain on recovery, PLAN §6.4); file-only mode (no backend enabled, capture off)
	// is unaffected.
	if c.CaptureEnabled && !c.MongoEnabled {
		return fmt.Errorf("config: capture enabled but the archive (mongo) backend is not enabled (archive-committed is the required terminal for captured history)")
	}
	return nil
}

// Capacity accounting ---------------------------------------------------------

// Admission is the result of a capacity check performed BEFORE accepting a record.
type Admission struct {
	Allowed bool
	Warning bool   // at/above warn threshold but still admitting
	Reason  string // populated when not allowed
}

// Usage is the current measured usage the accountant checks against.
type Usage struct {
	LiveBytes int64 // current live data bytes (archive + index + control + dedup metadata)
	WALBytes  int64 // current bytes held in the WAL
	FreeBytes int64 // current free filesystem bytes on the state volume
}

// Accountant enforces D4 bounds. It NEVER evicts; it only admits or rejects.
type Accountant struct{ cfg Config }

func NewAccountant(c Config) *Accountant { return &Accountant{cfg: c} }

// Admit decides whether a new record of recordBytes may be accepted, reserving
// capacity BEFORE acceptance. A full live cap, exhausted WAL budget, or
// insufficient free headroom rejects intake with a distinct reason; it must never
// be resolved by discarding already-accepted data.
func (a *Accountant) Admit(u Usage, recordBytes int64) Admission {
	if recordBytes < 0 || u.WALBytes < 0 || u.LiveBytes < 0 || u.FreeBytes < 0 {
		return Admission{Allowed: false, Reason: "NOT_ACCEPTED_INVALID: negative size or measured usage"}
	}
	if u.WALBytes > a.cfg.WALBytes || recordBytes > a.cfg.WALBytes-u.WALBytes {
		return Admission{Allowed: false, Reason: "NOT_ACCEPTED_BACKPRESSURE: WAL bound would be exceeded"}
	}
	if u.LiveBytes > a.cfg.LiveCapBytes || recordBytes > a.cfg.LiveCapBytes-u.LiveBytes {
		return Admission{Allowed: false, Reason: "NOT_ACCEPTED_BACKPRESSURE: live-data cap would be exceeded"}
	}
	if u.FreeBytes < a.cfg.FreeHeadroom || recordBytes > u.FreeBytes-a.cfg.FreeHeadroom {
		return Admission{Allowed: false, Reason: "NOT_ACCEPTED_UNAVAILABLE: free-space headroom would be breached"}
	}
	warn := float64(u.LiveBytes+recordBytes) >= a.cfg.WarnFraction*float64(a.cfg.LiveCapBytes)
	return Admission{Allowed: true, Warning: warn}
}

// WALMaintenanceLimit is the existing configured WAL cap, not extra scratch space.
func (a *Accountant) WALMaintenanceLimit() int64 { return a.cfg.WALBytes }

// MaintenancePeak bounds temporary managed-byte growth against the CURRENT live
// usage and filesystem headroom as well as the WAL cap. No WAL-cost proxy is used
// for staging: PlanCompaction checks its exact encoded files against this ceiling.
func (a *Accountant) MaintenancePeak(u Usage, currentWAL int64) (int64, error) {
	if currentWAL < 0 || currentWAL > a.cfg.WALBytes || u.LiveBytes < 0 || u.LiveBytes > a.cfg.LiveCapBytes || u.FreeBytes < a.cfg.FreeHeadroom {
		return 0, fmt.Errorf("maintenance: capacity unavailable")
	}
	remaining := a.cfg.LiveCapBytes - u.LiveBytes
	if free := u.FreeBytes - a.cfg.FreeHeadroom; free < remaining {
		remaining = free
	}
	if walRemaining := a.cfg.WALBytes - currentWAL; walRemaining < remaining {
		remaining = walRemaining
	}
	return currentWAL + remaining, nil
}

// AdmitGrowth separates journal bytes from ALL live growth; the live cap is one
// shared budget, never a separate allowance per archive/index/control component.
func (a *Accountant) AdmitGrowth(u Usage, walGrowth, liveGrowth int64) Admission {
	if walGrowth < 0 || liveGrowth < walGrowth {
		return Admission{Reason: "NOT_ACCEPTED_INVALID: invalid growth plan"}
	}
	admission := Admission{}
	if u.WALBytes < 0 || u.LiveBytes < 0 || u.FreeBytes < 0 {
		return Admission{Reason: "NOT_ACCEPTED_INVALID: negative usage"}
	}
	if u.WALBytes > a.cfg.WALBytes || walGrowth > a.cfg.WALBytes-u.WALBytes {
		return Admission{Reason: "NOT_ACCEPTED_BACKPRESSURE: WAL bound would be exceeded"}
	}
	if u.LiveBytes > a.cfg.LiveCapBytes || liveGrowth > a.cfg.LiveCapBytes-u.LiveBytes {
		return Admission{Reason: "NOT_ACCEPTED_BACKPRESSURE: live-data cap would be exceeded"}
	}
	if u.FreeBytes < a.cfg.FreeHeadroom || liveGrowth > u.FreeBytes-a.cfg.FreeHeadroom {
		return Admission{Reason: "NOT_ACCEPTED_UNAVAILABLE: free-space headroom would be breached"}
	}
	admission.Allowed = true
	admission.Reason = ""
	admission.Warning = float64(u.LiveBytes+liveGrowth) >= a.cfg.WarnFraction*float64(a.cfg.LiveCapBytes)
	return admission
}

// MaintenancePeakWithPending keeps already-promised projection capacity out of
// temporary-generation headroom. Pending bytes are a live/free liability, never
// an extra WAL allocation. The caller serializes measurement reconciliation and
// maintenance with all other writers.
func (a *Accountant) MaintenancePeakWithPending(u Usage, currentWAL, pending int64) (int64, error) {
	if pending < 0 || u.LiveBytes < 0 || u.LiveBytes > a.cfg.LiveCapBytes || pending > a.cfg.LiveCapBytes-u.LiveBytes || u.FreeBytes < 0 || pending > u.FreeBytes {
		return 0, fmt.Errorf("maintenance: pending reservations exceed capacity")
	}
	u.LiveBytes += pending
	u.FreeBytes -= pending
	return a.MaintenancePeak(u, currentWAL)
}
