// Package retention implements deletion barriers, the serve gate, and restore rules
// (PLAN §11.1, R3). Deleting a capture writes a durable TOMBSTONE (deletion barrier)
// that is retained and OUTLIVES every restorable backup. Serving filters out
// bar+revoked content. A RESTORE re-applies the latest barriers AND the latest
// consent/grant epochs BEFORE serving, so a stale backup can never resurrect deleted
// or revoked content. Backup expiry (D4: 30 days / 20 GiB) never shortens retention
// of accepted live data and never erases barriers.
package retention

import (
	"time"

	"aifactory.local/storage/internal/archive"
	"aifactory.local/storage/internal/registry"
)

// Scope identifies what a barrier deletes.
type Scope string

const (
	ScopeProject Scope = "project" // all captures for a project
	ScopeSession Scope = "session" // a single session
)

// Barrier is a durable deletion record. It is retained indefinitely (outlives
// backups) so restores cannot resurrect deleted data.
type Barrier struct {
	Project   string
	Scope     Scope
	SessionID string // for ScopeSession
	Epoch     int64  // consent/deletion epoch at deletion time
	CreatedAt time.Time
}

// Manager holds the retained barrier log and references the registry for the
// latest consent epochs.
type Manager struct {
	reg      *registry.Registry
	barriers []Barrier
	now      func() time.Time
}

func New(reg *registry.Registry) *Manager {
	return &Manager{reg: reg, now: time.Now}
}

func (m *Manager) SetClock(f func() time.Time) { m.now = f }

// DeleteProject records a project-scope deletion barrier. Operator-only is enforced
// at the API/registry layer; here the barrier is appended to the retained log.
func (m *Manager) DeleteProject(project string, epoch int64) Barrier {
	b := Barrier{Project: project, Scope: ScopeProject, Epoch: epoch, CreatedAt: m.now()}
	m.barriers = append(m.barriers, b)
	return b
}

// DeleteSession records a session-scope deletion barrier.
func (m *Manager) DeleteSession(project, session string, epoch int64) Barrier {
	b := Barrier{Project: project, Scope: ScopeSession, SessionID: session, Epoch: epoch, CreatedAt: m.now()}
	m.barriers = append(m.barriers, b)
	return b
}

// Barriers returns the retained barrier log (never erased by backup expiry).
func (m *Manager) Barriers() []Barrier { return m.barriers }

// Serve applies the deletion barriers and the latest consent cutoff to a raw record
// set, returning only records that may be served. A record is withheld if:
//   - a project barrier exists for its project, OR
//   - a session barrier exists for its (project, session), OR
//   - its consent for (project, provider, capability "capture") is currently
//     disabled and the record's ConsentEpoch is at/below that revocation epoch.
func (m *Manager) Serve(records []archive.Record, capability string) []archive.Record {
	var out []archive.Record
	for _, r := range records {
		if m.barred(r) {
			continue
		}
		c := m.reg.ConsentEpoch(r.Project, r.Provider, capability)
		if !c.Enabled && r.ConsentEpoch <= c.Epoch && c.Epoch > 0 {
			continue // collected under a now-revoked consent
		}
		out = append(out, r)
	}
	return out
}

func (m *Manager) barred(r archive.Record) bool {
	for _, b := range m.barriers {
		if b.Project != r.Project {
			continue
		}
		switch b.Scope {
		case ScopeProject:
			return true
		case ScopeSession:
			if b.SessionID == r.SessionID {
				return true
			}
		}
	}
	return false
}

// Restore re-applies barriers and current consent to records loaded from a backup and
// returns only what may be served. Unlike Serve (live serving of already-admitted
// data), Restore is a REPLAY ADMISSION GATE and FAILS CLOSED: a record is withheld
// unless the registry positively establishes current authority for it. A record is
// served only when ALL hold:
//   - its project is known to the registry;
//   - consent for (project, provider, capability) has been established (epoch > 0) and
//     is currently enabled;
//   - the record was collected under exactly the current consent epoch — a record from
//     a superseded (pre-revocation) epoch is NOT resurrected by a later re-enable, and
//     a record claiming a future epoch is rejected;
//   - no deletion barrier covers it.
//
// Draining pre-revocation records requires explicit, separate authorization (not yet
// implemented); Restore never does it implicitly. The durable barrier/consent state
// this gate reads is in-memory only today (see registry STATUS); until the D3 durable
// boundary exists this must not be relied on as a cross-process worker admission gate.
func (m *Manager) Restore(backupRecords []archive.Record, capability string) []archive.Record {
	var out []archive.Record
	for _, r := range backupRecords {
		if m.barred(r) {
			continue
		}
		if !m.reg.HasProject(r.Project) {
			continue // fail closed: unknown project / authority
		}
		c := m.reg.ConsentEpoch(r.Project, r.Provider, capability)
		if c.Epoch == 0 || !c.Enabled {
			continue // never established, or currently revoked
		}
		if r.ConsentEpoch != c.Epoch {
			continue // pre-revocation (stale) or future epoch: not re-authorized here
		}
		out = append(out, r)
	}
	return out
}

// BackupExpired reports whether a backup taken at t is past the configured max age.
func BackupExpired(t time.Time, now time.Time, maxAgeDays int) bool {
	return now.Sub(t) > time.Duration(maxAgeDays)*24*time.Hour
}
