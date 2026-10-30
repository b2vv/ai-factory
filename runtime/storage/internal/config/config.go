// Package config holds the pilot defaults (owner decision D4) and the capacity
// accounting used to enforce bounded storage WITHOUT evicting accepted records.
package config

import "fmt"

// Pilot defaults from D4. All are configurable; these are starting limits to
// validate under synthetic load, not measured production sizing.
const (
	DefaultWALBytes        int64 = 256 * 1024 * 1024       // 256 MiB write-ahead log
	DefaultLiveCapBytes    int64 = 10 * 1024 * 1024 * 1024 // 10 GiB live data (incl. DB/index/control/dedup metadata)
	DefaultWarnFraction          = 0.80                    // warn at 80% of live cap
	DefaultFreeHeadroom    int64 = 1 * 1024 * 1024 * 1024  // keep 1 GiB filesystem free
	DefaultBackupMaxAgeDays       = 30                      // backups expire after 30 days
	DefaultBackupBudget    int64 = 20 * 1024 * 1024 * 1024 // 20 GiB backup budget (separately accounted)
)

// Config is the effective runtime configuration. Modules are disabled by default.
type Config struct {
	// Capability switches — all OFF by default (owner must enable each).
	MongoEnabled   bool
	PostgresEnabled bool
	CaptureEnabled bool // conversation capture; off by default and gated further by consent

	// D4 capacity/privacy.
	WALBytes        int64
	LiveCapBytes    int64
	WarnFraction    float64
	FreeHeadroom    int64
	BackupMaxAgeDays int
	BackupBudget    int64

	AutoMessageTTL  bool // D4: no automatic message-age TTL -> false
	BackfillEnabled bool // D4: historical backfill disabled -> false
	HookGapOnly     bool // D4: gap-only hooks, no client transcript spool -> true
}

// Default returns the owner-approved pilot defaults with every capability disabled.
func Default() Config {
	return Config{
		MongoEnabled:    false,
		PostgresEnabled: false,
		CaptureEnabled:  false,
		WALBytes:        DefaultWALBytes,
		LiveCapBytes:    DefaultLiveCapBytes,
		WarnFraction:    DefaultWarnFraction,
		FreeHeadroom:    DefaultFreeHeadroom,
		BackupMaxAgeDays: DefaultBackupMaxAgeDays,
		BackupBudget:    DefaultBackupBudget,
		AutoMessageTTL:  false,
		BackfillEnabled: false,
		HookGapOnly:     true,
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
	return nil
}

// Capacity accounting ---------------------------------------------------------

// Admission is the result of a capacity check performed BEFORE accepting a record.
type Admission struct {
	Allowed bool
	Warning bool   // at/над warn threshold but still admitting
	Reason  string // populated when not allowed
}

// Usage is the current measured usage the accountant checks against.
type Usage struct {
	LiveBytes     int64 // current live data bytes (archive + index + control + dedup metadata)
	WALBytes      int64 // current bytes held in the WAL
	FreeBytes     int64 // current free filesystem bytes on the state volume
}

// Accountant enforces D4 bounds. It NEVER evicts; it only admits or rejects.
type Accountant struct{ cfg Config }

func NewAccountant(c Config) *Accountant { return &Accountant{cfg: c} }

// Admit decides whether a new record of recordBytes may be accepted, reserving
// capacity BEFORE acceptance. A full live cap, exhausted WAL budget, or
// insufficient free headroom rejects intake with a distinct reason; it must never
// be resolved by discarding already-accepted data.
func (a *Accountant) Admit(u Usage, recordBytes int64) Admission {
	if recordBytes < 0 {
		return Admission{Allowed: false, Reason: "NOT_ACCEPTED_INVALID: negative record size"}
	}
	if u.WALBytes+recordBytes > a.cfg.WALBytes {
		return Admission{Allowed: false, Reason: "NOT_ACCEPTED_BACKPRESSURE: WAL bound would be exceeded"}
	}
	if u.LiveBytes+recordBytes > a.cfg.LiveCapBytes {
		return Admission{Allowed: false, Reason: "NOT_ACCEPTED_BACKPRESSURE: live-data cap would be exceeded"}
	}
	if u.FreeBytes-recordBytes < a.cfg.FreeHeadroom {
		return Admission{Allowed: false, Reason: "NOT_ACCEPTED_UNAVAILABLE: free-space headroom would be breached"}
	}
	warn := float64(u.LiveBytes+recordBytes) >= a.cfg.WarnFraction*float64(a.cfg.LiveCapBytes)
	return Admission{Allowed: true, Warning: warn}
}
