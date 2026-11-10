package control

import (
	"aifactory.local/storage/internal/registry"
	"encoding/json"
	"errors"
	"unicode/utf8"
)

// ArchiveState is control authority for an explicitly activated metadata epoch.
// This API is not wired to the running server or operator activation yet.
type ArchiveState struct {
	ProjectionCancellationBytes int64 `json:",omitempty"`
	ProjectionCancelled         bool  `json:",omitempty"`
	Projection                  *ArchiveProjection
	Pending                     *ArchiveOperation
	Last                        *ArchiveOperation
	LastCommitted               bool
	Version                     int
	Generation                  string
	MigrationComplete           bool
	NextOrdinal                 int64
	CommittedOrdinal            int64
	PolicyRevision              uint64
}

func validArchiveGeneration(g string) bool { return len(g) > 0 && len(g) <= 128 && utf8.ValidString(g) }
func (d *Durable) applyArchiveBegin(project, generation string) error {
	if !d.reg.HasProject(project) || !validArchiveGeneration(generation) {
		return errors.New("control: invalid archive migration")
	}
	if _, exists := d.archiveStates[project]; exists {
		return errors.New("control: archive metadata epoch already exists")
	}
	if d.archiveStates == nil {
		d.archiveStates = map[string]ArchiveState{}
	}
	d.archiveStates[project] = ArchiveState{Version: 2, Generation: generation, NextOrdinal: 1}
	return nil
}

// BeginArchiveMigration persists the compatibility witness before any backend
// mutation. Repeating the same request is a no-op; epoch replacement is refused.
func (d *Durable) BeginArchiveMigration(actor registry.Principal, project, generation string) error {
	d.mu.Lock()
	defer d.mu.Unlock()
	if err := d.ready(); err != nil {
		return err
	}
	if actor.Kind != registry.Operator {
		return registry.ErrNotOperator
	}
	if !d.reg.HasProject(project) || !validArchiveGeneration(generation) {
		return errors.New("control: invalid archive migration")
	}
	if old, ok := d.archiveStates[project]; ok {
		if old.Generation == generation {
			return nil
		}
		return errors.New("control: archive metadata epoch already exists")
	}
	if err := d.persist(mutation{Kind: kArchiveBegin, Project: project, ArchiveGeneration: generation}); err != nil {
		return err
	}
	return d.applyArchiveBegin(project, generation)
}
func (d *Durable) ArchiveState(project string) (ArchiveState, bool, error) {
	d.mu.Lock()
	defer d.mu.Unlock()
	if err := d.ready(); err != nil {
		return ArchiveState{}, false, err
	}
	s, ok := d.archiveStates[project]
	raw, _ := json.Marshal(s)
	var detached ArchiveState
	if err := json.Unmarshal(raw, &detached); err != nil {
		return ArchiveState{}, false, err
	}
	return detached, ok, nil
}

func (d *Durable) advanceArchivePolicy(project string) error {
	s, ok := d.archiveStates[project]
	if !ok {
		return nil
	}
	if s.PolicyRevision == ^uint64(0) {
		d.block("archive policy revision exhausted")
		return ErrBlocked
	}
	s.PolicyRevision++
	d.archiveStates[project] = s
	return nil
}
