// Package registry is the single local control authority (owner decision D3) for
// project identity, checkout enrollment, consent epochs, grants, and per-project
// workflow ownership. It is authoritative in ALL deployment modes (file-only,
// Mongo, Postgres) and never migrates into a database. All MUTATIONS are
// operator-only and serialized; agents may not self-issue grants or enroll.
//
// Three identities are kept distinct (R6): ProjectUUID (portable project key),
// Location (machine+checkout enrollment), and the existing guard session identity
// (owned by the untouched session-size-docker guard, never recomputed here).
package registry

import (
	"errors"
	"fmt"
	"sync"
	"time"
)

// Op is a scoped operation class used by both grants and authorization.
type Op string

const (
	OpEnroll        Op = "enroll"         // operator-only
	OpGrantAdmin    Op = "grant.admin"    // operator-only (issue/rotate/revoke)
	OpConsentSet    Op = "consent.set"    // operator-only
	OpDelete        Op = "delete"         // operator-only
	OpCrossProject  Op = "cross_project"  // operator-only
	OpCapture       Op = "capture"        // agent, within granted project
	OpArchiveQuery  Op = "archive.query"  // agent, within granted project
	OpSearch        Op = "search"         // agent, within granted project
	OpWorkflowRead  Op = "workflow.read"  // agent, within granted project
	OpWorkflowWrite Op = "workflow.write" // agent, within granted project
)

// knownOps is the closed set of valid operation classes; grants referencing anything
// outside it are rejected so a caller-supplied map cannot smuggle in an unknown op.
var knownOps = map[Op]bool{
	OpEnroll: true, OpGrantAdmin: true, OpConsentSet: true, OpDelete: true,
	OpCrossProject: true, OpCapture: true, OpArchiveQuery: true, OpSearch: true,
	OpWorkflowRead: true, OpWorkflowWrite: true,
}

// PrincipalKind distinguishes operator/admin authority from agent grants (R4).
type PrincipalKind string

const (
	Operator PrincipalKind = "operator"
	Agent    PrincipalKind = "agent"
)

// Principal identifies the caller. Possession of a project UUID is NOT authority;
// authorization is always principal+project+operation (see internal/authz).
type Principal struct {
	ID   string
	Kind PrincipalKind
}

// WorkflowOwner is the authoritative store for a project's structured workflow.
type WorkflowOwner string

const (
	OwnerMarkdown WorkflowOwner = "markdown" // D2 default
	OwnerPostgres WorkflowOwner = "postgres" // explicit reversible per-project opt-in
)

// LocationStatus records enrollment resolution for a checkout.
type LocationStatus string

const (
	LocEnrolled    LocationStatus = "enrolled"
	LocQuarantined LocationStatus = "quarantined" // ambiguous copied identity; needs operator decision
)

type Project struct {
	UUID    string
	Label   string
	Created time.Time
}

type Location struct {
	MachineID       string
	CheckoutPath    string
	Worktree        string
	GitRootResolved string
	Status          LocationStatus
	FirstSeen       time.Time
	LastSeen        time.Time
}

// Consent is epoch-versioned (R3). Every captured record is stamped with the epoch
// under which it was collected; a revocation bumps the epoch and sets Enabled=false.
type Consent struct {
	Enabled   bool
	Epoch     int64
	UpdatedAt time.Time
}

type consentKey struct {
	project, provider, capability string
}

// Grant binds a principal to allowed projects and operations, epoch-versioned so a
// stale (revoked / superseded) grant is rejected.
type Grant struct {
	PrincipalID string
	Kind        PrincipalKind
	Projects    map[string]bool
	Ops         map[Op]bool
	Epoch       int64
	Revoked     bool
	Secret      string // opaque token secret; delivered by 0600-file reference, never logged
}

type workflowAuthority struct {
	Owner WorkflowOwner
	Epoch int64 // authority/cutover epoch; bumped on every ownership transition
}

var (
	ErrNotOperator  = errors.New("registry: operation is operator-only")
	ErrUnknownProj  = errors.New("registry: unknown project")
	ErrDupUUID      = errors.New("registry: duplicate project UUID for an unrelated location; quarantined, operator must resolve")
	ErrGrantRevoked = errors.New("registry: grant revoked or superseded")
	// ErrWorkflowFenced means the project's workflow authority is no longer Postgres
	// at the writer's epoch at commit time (a cutover raced the write).
	ErrWorkflowFenced = errors.New("registry: workflow authority changed before commit (fenced)")
)

// Registry is the in-memory control authority with a serialized mutation lock.
//
// STATUS (WIP): this type is IN-MEMORY ONLY. Durable JSON snapshot/restore and the
// shared inter-process deletion/consent log (owner decision D3) are NOT_IMPLEMENTED
// yet; do not treat this as a durable service or a worker replay-admission authority
// until that boundary exists. Mutations are operator-only and serialized.
type Registry struct {
	mu        sync.Mutex
	projects  map[string]Project
	locations map[string][]Location // keyed by project UUID
	consent   map[consentKey]Consent
	grants    map[string]Grant // keyed by principal ID
	authority map[string]workflowAuthority
	now       func() time.Time
}

func New() *Registry {
	return &Registry{
		projects:  map[string]Project{},
		locations: map[string][]Location{},
		consent:   map[consentKey]Consent{},
		grants:    map[string]Grant{},
		authority: map[string]workflowAuthority{},
		now:       time.Now,
	}
}

// SetClock is a test seam.
func (r *Registry) SetClock(f func() time.Time) { r.now = f }

func requireOperator(actor Principal) error {
	if actor.Kind != Operator {
		return ErrNotOperator
	}
	return nil
}

// MintProject creates a project UUID. Operator-only.
func (r *Registry) MintProject(actor Principal, uuid, label string) error {
	if err := requireOperator(actor); err != nil {
		return err
	}
	r.mu.Lock()
	defer r.mu.Unlock()
	if uuid == "" {
		return fmt.Errorf("registry: empty project UUID")
	}
	if _, ok := r.projects[uuid]; ok {
		return fmt.Errorf("registry: project already exists")
	}
	r.projects[uuid] = Project{UUID: uuid, Label: label, Created: r.now()}
	r.authority[uuid] = workflowAuthority{Owner: OwnerMarkdown, Epoch: 1} // D2 default
	return nil
}

// EnrollLocation records a checkout for a project. Operator-only. An identical
// project UUID arriving from a location whose git root does not match any known
// location is treated as AMBIGUOUS and quarantined rather than silently merged
// (R6: no automatic clone-vs-fork detection). Returns the resolved status.
func (r *Registry) EnrollLocation(actor Principal, uuid string, loc Location, confirmSameProject bool) (LocationStatus, error) {
	if err := requireOperator(actor); err != nil {
		return "", err
	}
	r.mu.Lock()
	defer r.mu.Unlock()
	if _, ok := r.projects[uuid]; !ok {
		return "", ErrUnknownProj
	}
	loc.FirstSeen, loc.LastSeen = r.now(), r.now()
	existing := r.locations[uuid]
	// Only an already-ENROLLED matching location makes this an idempotent re-enroll.
	// A matching QUARANTINED location does NOT count as "known": it still requires
	// explicit operator resolution and must not self-upgrade on a bare retry.
	enrolledMatch := false
	quarantinedMatch := false
	for _, e := range existing {
		if e.GitRootResolved == loc.GitRootResolved && e.MachineID == loc.MachineID {
			switch e.Status {
			case LocEnrolled:
				enrolledMatch = true
			case LocQuarantined:
				quarantinedMatch = true
			}
		}
	}
	if enrolledMatch {
		return LocEnrolled, nil // already enrolled; no duplicate entry appended
	}
	// A quarantined match resolves to enrolled ONLY on an explicit operator
	// confirmation; a bare retry stays quarantined (no new entry appended).
	if quarantinedMatch {
		if !confirmSameProject {
			return LocQuarantined, ErrDupUUID
		}
		for i := range existing {
			if existing[i].GitRootResolved == loc.GitRootResolved && existing[i].MachineID == loc.MachineID && existing[i].Status == LocQuarantined {
				existing[i].Status = LocEnrolled
				existing[i].LastSeen = r.now()
			}
		}
		r.locations[uuid] = existing
		return LocEnrolled, nil
	}
	// A brand-new location for a UUID that is already enrolled elsewhere is
	// ambiguous unless the operator explicitly confirms it is the same project.
	if len(existing) > 0 && !confirmSameProject {
		loc.Status = LocQuarantined
		r.locations[uuid] = append(existing, loc)
		return LocQuarantined, ErrDupUUID
	}
	loc.Status = LocEnrolled
	r.locations[uuid] = append(existing, loc)
	return LocEnrolled, nil
}

// SetConsent sets (or revokes) a per project/provider/capability consent and bumps
// its epoch. Operator-only. Returns the new epoch.
func (r *Registry) SetConsent(actor Principal, project, provider, capability string, enabled bool) (int64, error) {
	if err := requireOperator(actor); err != nil {
		return 0, err
	}
	r.mu.Lock()
	defer r.mu.Unlock()
	if _, ok := r.projects[project]; !ok {
		return 0, ErrUnknownProj
	}
	k := consentKey{project, provider, capability}
	c := r.consent[k]
	c.Epoch++
	c.Enabled = enabled
	c.UpdatedAt = r.now()
	r.consent[k] = c
	return c.Epoch, nil
}

// ConsentEpoch returns the current consent record (default: disabled, epoch 0).
func (r *Registry) ConsentEpoch(project, provider, capability string) Consent {
	r.mu.Lock()
	defer r.mu.Unlock()
	return r.consent[consentKey{project, provider, capability}]
}

// copyGrant deep-copies the mutable maps of a grant so stored authority can never be
// aliased by (nor leaked to) a caller's map reference.
func copyGrant(g Grant) Grant {
	projects := make(map[string]bool, len(g.Projects))
	for k, v := range g.Projects {
		projects[k] = v
	}
	ops := make(map[Op]bool, len(g.Ops))
	for k, v := range g.Ops {
		ops[k] = v
	}
	g.Projects = projects
	g.Ops = ops
	return g
}

// ValidateGrant checks a grant's static validity WITHOUT mutating or locking the registry:
// a recognized principal kind, only known operations, and no operator-only op on an agent
// grant. It is the single source of truth for grant validity, callable BEFORE a durable
// persist so an invalid grant is rejected without ever writing a journal record (a durable
// but un-appliable grant record would fail replay and make the server unstartable).
func ValidateGrant(g Grant) error {
	if g.Kind != Operator && g.Kind != Agent {
		return fmt.Errorf("registry: invalid principal kind %q", g.Kind)
	}
	for op := range g.Ops {
		if !knownOps[op] {
			return fmt.Errorf("registry: unknown operation %q in grant", op)
		}
		if g.Kind == Agent {
			switch op {
			case OpEnroll, OpGrantAdmin, OpConsentSet, OpDelete, OpCrossProject:
				return fmt.Errorf("registry: agent grant may not include operator-only op %q", op)
			}
		}
	}
	return nil
}

// IssueGrant creates/updates a grant. Operator-only. An agent principal can never
// be granted operator-only operations. The caller's maps are DEEP-COPIED so a later
// mutation of the caller-owned map cannot change stored authorization.
func (r *Registry) IssueGrant(actor Principal, g Grant) error {
	if err := requireOperator(actor); err != nil {
		return err
	}
	if err := ValidateGrant(g); err != nil {
		return err
	}
	r.mu.Lock()
	defer r.mu.Unlock()
	stored := copyGrant(g)
	prev := r.grants[g.PrincipalID]
	stored.Epoch = prev.Epoch + 1
	r.grants[g.PrincipalID] = stored
	return nil
}

// RevokeGrant marks a principal's grant revoked (and bumps epoch). Operator-only.
func (r *Registry) RevokeGrant(actor Principal, principalID string) error {
	if err := requireOperator(actor); err != nil {
		return err
	}
	r.mu.Lock()
	defer r.mu.Unlock()
	g, ok := r.grants[principalID]
	if !ok {
		return fmt.Errorf("registry: no such grant")
	}
	g.Revoked = true
	g.Epoch++
	r.grants[principalID] = g
	return nil
}

// Lookup returns a DEEP COPY of a grant and whether it exists. Mutating the returned
// Projects/Ops maps can never change stored authorization.
func (r *Registry) Lookup(principalID string) (Grant, bool) {
	r.mu.Lock()
	defer r.mu.Unlock()
	g, ok := r.grants[principalID]
	if !ok {
		return Grant{}, false
	}
	return copyGrant(g), true
}

// HasProject reports whether a project UUID is known to the registry. Used by callers
// (e.g. the retention/restore gate) that must fail closed on unknown authority.
func (r *Registry) HasProject(uuid string) bool {
	r.mu.Lock()
	defer r.mu.Unlock()
	_, ok := r.projects[uuid]
	return ok
}

// WorkflowAuthority returns the current owner and authority epoch for a project.
func (r *Registry) WorkflowAuthority(project string) (WorkflowOwner, int64, bool) {
	r.mu.Lock()
	defer r.mu.Unlock()
	a, ok := r.authority[project]
	return a.Owner, a.Epoch, ok
}

// FenceWorkflowCommit runs commit UNDER the authority mutation lock, so no cutover
// (FlipWorkflowAuthority) can interleave between the authority check and the store
// commit. It verifies, while holding the lock, that project is still Postgres-
// authoritative at exactly writerEpoch, then calls commit with the lock still held;
// a concurrent cutover blocks until commit returns. This closes the check-then-commit
// race in internal/workflow.
//
// commit MUST NOT call back into this Registry (the mutation lock is held and is not
// reentrant).
func (r *Registry) FenceWorkflowCommit(project string, writerEpoch int64, commit func() error) error {
	r.mu.Lock()
	defer r.mu.Unlock()
	a, ok := r.authority[project]
	if !ok {
		return ErrUnknownProj
	}
	if a.Owner != OwnerPostgres || a.Epoch != writerEpoch {
		return ErrWorkflowFenced
	}
	return commit()
}

// FlipWorkflowAuthority atomically transitions ownership and bumps the epoch.
// Operator-only. The caller is responsible for having quiesced/fenced and written
// a cutover receipt first (see internal/workflow).
func (r *Registry) FlipWorkflowAuthority(actor Principal, project string, to WorkflowOwner) (int64, error) {
	if err := requireOperator(actor); err != nil {
		return 0, err
	}
	r.mu.Lock()
	defer r.mu.Unlock()
	a, ok := r.authority[project]
	if !ok {
		return 0, ErrUnknownProj
	}
	a.Owner = to
	a.Epoch++
	r.authority[project] = a
	return a.Epoch, nil
}

// Projects lists known project UUIDs (read-only, any caller).
func (r *Registry) Projects() []string {
	r.mu.Lock()
	defer r.mu.Unlock()
	out := make([]string, 0, len(r.projects))
	for u := range r.projects {
		out = append(out, u)
	}
	return out
}
