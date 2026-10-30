// Package workflow implements reversible per-project workflow ownership (D2, PLAN
// §3.3). Markdown is authoritative by default; a project may be explicitly opted
// into PostgreSQL-owned structured workflow via a cutover. Writes are protected by
// BOTH a per-entity version compare-and-set (prevents lost updates between agents)
// AND an authority/cutover epoch (fences a delayed pre-cutover writer from landing
// after the authority flip). Exactly one store is authoritative at any instant.
package workflow

import (
	"errors"

	"aifactory.local/storage/internal/registry"
)

var (
	ErrNotPGOwned    = errors.New("workflow: project is Markdown-authoritative; PG writes not permitted")
	ErrBlockedPGDown = errors.New("workflow: PostgreSQL unavailable; BLOCKED (no fabricated export/restore)")
	ErrStaleEpoch    = errors.New("workflow: writer epoch does not match current authority epoch (fenced)")
	ErrStaleVersion  = errors.New("workflow: entity version precondition failed (stale write rejected)")
)

// Task is a structured workflow entity.
type Task struct {
	ID      string
	Version int64
	Fields  map[string]string
}

// Store is the PG-backed structured store (faked in tests).
type Store interface {
	Available() bool
	Get(project, id string) (Task, bool)
	CAS(project string, t Task, expectedVersion int64) error
}

// CutoverReceipt records an ownership transition for crash-safe recovery (§3.3).
type CutoverReceipt struct {
	Project    string
	From       registry.WorkflowOwner
	To         registry.WorkflowOwner
	OldEpoch   int64
	NewEpoch   int64
	ExportHash string // hash of the verified export produced during quiesce
}

// Manager mediates workflow writes and ownership transitions.
type Manager struct {
	reg   *registry.Registry
	store Store
}

func New(reg *registry.Registry, store Store) *Manager { return &Manager{reg: reg, store: store} }

// Write applies a structured workflow update under full fencing. writerEpoch is the
// authority epoch the caller believes is current; a stale value (e.g. a pre-cutover
// writer resuming after the flip) is rejected. The store commit itself runs under the
// registry's authority lock (FenceWorkflowCommit), so a cutover cannot interleave
// between the epoch check and the commit: the authority is re-verified at commit time
// and a concurrent flip blocks until the commit completes.
func (m *Manager) Write(project, id string, expectedVersion, writerEpoch int64, fields map[string]string) error {
	// Fail-fast pre-checks (cheap rejects before taking the authority lock).
	owner, epoch, ok := m.reg.WorkflowAuthority(project)
	if !ok {
		return registry.ErrUnknownProj
	}
	if owner != registry.OwnerPostgres {
		return ErrNotPGOwned
	}
	if writerEpoch != epoch {
		return ErrStaleEpoch
	}
	if !m.store.Available() {
		return ErrBlockedPGDown
	}

	// Commit-time fence: authority is re-checked while the commit runs under the lock.
	err := m.reg.FenceWorkflowCommit(project, writerEpoch, func() error {
		if !m.store.Available() {
			return ErrBlockedPGDown
		}
		cur, _ := m.store.Get(project, id)
		if cur.Version != expectedVersion {
			return ErrStaleVersion
		}
		next := Task{ID: id, Version: expectedVersion + 1, Fields: fields}
		return m.store.CAS(project, next, expectedVersion)
	})
	if err == registry.ErrWorkflowFenced {
		return ErrStaleEpoch // a cutover raced the write; reject as stale
	}
	return err
}

// EnablePG performs the Markdown->Postgres cutover: quiesce (caller stops writes),
// import validation + export hash supplied by caller, then an atomic authority flip
// that bumps the epoch, fencing any in-flight pre-cutover writer. Operator-only via
// the registry. Returns the receipt.
func (m *Manager) EnablePG(actor registry.Principal, project, exportHash string) (CutoverReceipt, error) {
	owner, oldEpoch, ok := m.reg.WorkflowAuthority(project)
	if !ok {
		return CutoverReceipt{}, registry.ErrUnknownProj
	}
	if !m.store.Available() {
		return CutoverReceipt{}, ErrBlockedPGDown
	}
	newEpoch, err := m.reg.FlipWorkflowAuthority(actor, project, registry.OwnerPostgres)
	if err != nil {
		return CutoverReceipt{}, err
	}
	return CutoverReceipt{Project: project, From: owner, To: registry.OwnerPostgres, OldEpoch: oldEpoch, NewEpoch: newEpoch, ExportHash: exportHash}, nil
}

// DisablePG performs the reversible Postgres->Markdown cutover: quiesce + export +
// verify (caller supplies the verified export hash), then flip authority back. If PG
// is unavailable the export cannot be verified, so ownership stays BLOCKED rather
// than claiming a successful return to file-only.
func (m *Manager) DisablePG(actor registry.Principal, project, verifiedExportHash string) (CutoverReceipt, error) {
	owner, oldEpoch, ok := m.reg.WorkflowAuthority(project)
	if !ok {
		return CutoverReceipt{}, registry.ErrUnknownProj
	}
	if owner != registry.OwnerPostgres {
		return CutoverReceipt{}, ErrNotPGOwned
	}
	if !m.store.Available() {
		return CutoverReceipt{}, ErrBlockedPGDown
	}
	if verifiedExportHash == "" {
		return CutoverReceipt{}, errors.New("workflow: refusing cutover without a verified export hash")
	}
	newEpoch, err := m.reg.FlipWorkflowAuthority(actor, project, registry.OwnerMarkdown)
	if err != nil {
		return CutoverReceipt{}, err
	}
	return CutoverReceipt{Project: project, From: owner, To: registry.OwnerMarkdown, OldEpoch: oldEpoch, NewEpoch: newEpoch, ExportHash: verifiedExportHash}, nil
}

// MemStore is an in-memory fake Store for the hermetic suite (no real PostgreSQL).
type MemStore struct {
	up    bool
	tasks map[string]Task
}

func NewMemStore() *MemStore { return &MemStore{up: true, tasks: map[string]Task{}} }

func (s *MemStore) SetAvailable(b bool) { s.up = b }
func (s *MemStore) Available() bool     { return s.up }
func (s *MemStore) Get(project, id string) (Task, bool) {
	t, ok := s.tasks[project+"/"+id]
	return t, ok
}
func (s *MemStore) CAS(project string, t Task, expectedVersion int64) error {
	cur := s.tasks[project+"/"+t.ID]
	if cur.Version != expectedVersion {
		return ErrStaleVersion
	}
	s.tasks[project+"/"+t.ID] = t
	return nil
}
