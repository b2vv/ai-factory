package config

import (
	"encoding/json"
	"fmt"
	"os"
)

// overlay is a partial, pointer-valued projection of Config used to apply only the
// fields a config file actually sets (absent fields keep the D4 default).
type overlay struct {
	MongoEnabled    *bool    `json:"mongo_enabled"`
	PostgresEnabled *bool    `json:"postgres_enabled"`
	CaptureEnabled  *bool    `json:"capture_enabled"`
	WALBytes        *int64   `json:"wal_bytes"`
	LiveCapBytes    *int64   `json:"live_cap_bytes"`
	WarnFraction    *float64 `json:"warn_fraction"`
	FreeHeadroom    *int64   `json:"free_headroom"`
}

// Load builds the effective configuration: start from the owner-approved D4 defaults
// (every capability disabled), apply an optional JSON file overlay, apply environment
// overrides, then Validate. A missing file is not an error; a malformed file is.
func Load(path string, getenv func(string) string) (Config, error) {
	c := Default()
	if path != "" {
		b, err := os.ReadFile(path)
		switch {
		case err == nil:
			var o overlay
			if err := json.Unmarshal(b, &o); err != nil {
				return Config{}, fmt.Errorf("config: malformed config file %s: %w", path, err)
			}
			applyOverlay(&c, o)
		case os.IsNotExist(err):
			// absent file: keep defaults
		default:
			return Config{}, err
		}
	}
	applyEnv(&c, getenv)
	if err := c.Validate(); err != nil {
		return Config{}, err
	}
	return c, nil
}

func applyOverlay(c *Config, o overlay) {
	if o.MongoEnabled != nil {
		c.MongoEnabled = *o.MongoEnabled
	}
	if o.PostgresEnabled != nil {
		c.PostgresEnabled = *o.PostgresEnabled
	}
	if o.CaptureEnabled != nil {
		c.CaptureEnabled = *o.CaptureEnabled
	}
	if o.WALBytes != nil {
		c.WALBytes = *o.WALBytes
	}
	if o.LiveCapBytes != nil {
		c.LiveCapBytes = *o.LiveCapBytes
	}
	if o.WarnFraction != nil {
		c.WarnFraction = *o.WarnFraction
	}
	if o.FreeHeadroom != nil {
		c.FreeHeadroom = *o.FreeHeadroom
	}
}

func applyEnv(c *Config, getenv func(string) string) {
	if getenv == nil {
		return
	}
	if v, ok := envBool(getenv("STORAGE_MONGO_ENABLED")); ok {
		c.MongoEnabled = v
	}
	if v, ok := envBool(getenv("STORAGE_POSTGRES_ENABLED")); ok {
		c.PostgresEnabled = v
	}
	if v, ok := envBool(getenv("STORAGE_CAPTURE_ENABLED")); ok {
		c.CaptureEnabled = v
	}
}

func envBool(s string) (bool, bool) {
	switch s {
	case "1", "true", "TRUE", "yes":
		return true, true
	case "0", "false", "FALSE", "no":
		return false, true
	default:
		return false, false
	}
}
