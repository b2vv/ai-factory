// Package control is the DURABLE wrapper around the in-memory control authority
// (registry) and the deletion-barrier log (retention). It persists every exposed
// authority mutation through the existing durable WAL (internal/wal) - reusing that
// journal's fsync boundaries, exact-key dedup and V3-1 fail-closed recovery rather
// than writing new journal code - and rebuilds authority on restart by replaying the
// accepted records.
//
// Durability contract (owner decision D3, minimal slice):
//   - Mutations are serialized (single writer) and acknowledged ONLY after the WAL
//     record is durably accepted (fsync'd).
//   - Authority-GRANTING mutations (mint/enroll/grant-issue/consent-enable) persist
//     BEFORE they are applied in memory, so a persistence failure never exposes an
//     uncommitted grant.
//   - Authority-REDUCING mutations (grant-revoke/consent-disable/deletion-barrier) are
//     applied in memory FIRST (so the running process immediately denies) and then
//     persisted; a persistence failure returns an error (NOT acknowledged) while the
//     in-memory state stays restrictive, so stale authority is never served after a
//     failed revocation.
//   - Corrupt/ambiguous durable state fails CLOSED (BLOCKED): the registry serves no
//     authority and refuses mutations until explicit operator recovery. It is NEVER
//     reset to a permissive empty state.
//   - First-time initialization is distinguished from missing/lost state for an
//     existing registry via a durable high-water marker, so deleting the log cannot
//     silently re-permit enrollment that bypasses prior revocations or deletion
//     barriers. Initialization is an EXPLICIT operator action (Initialize); ordinary Open
//     never creates authority and fails closed on an uninitialized or mistyped state path.
//
// BLOCKED is a terminal, fail-closed state, by design (documented trust boundary, E):
//   - When the durable log is ambiguous/corrupt/lost, the registry serves no authority and
//     refuses every mutation. There is deliberately no automated un-block path here: a torn
//     write in the middle of a mutation (a crash between the WAL frame fsync and the accept
//     fsync) leaves the journal ambiguous under the WAL's V3-1 rule, so the whole registry
//     is held BLOCKED (deny-all) rather than guess which partial mutation to keep. Deny-all
//     is the safe outcome; recovering a BLOCKED registry is a deliberate operator action
//     against the preserved on-disk journal, out of scope for this slice.
//   - Complete loss of ALL local evidence (state dir and marker both gone) is indistinguishable
//     from a genuine first run and is a documented trust boundary, not a detectable event:
//     Open then reports "not initialized" and Initialize would establish a new, empty registry.
//     Protecting against total local-evidence loss is an operational concern (backups/host
//     integrity), not something the process can detect from the surviving files alone.
package control

import (
	"crypto/rand"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"sync"
	"syscall"

	"aifactory.local/storage/internal/registry"
	"aifactory.local/storage/internal/retention"
	"aifactory.local/storage/internal/wal"
)

// ErrBlocked is returned by every mutation and should gate every authority read when
// the durable registry could not establish trustworthy state.
var ErrBlocked = errors.New("control: registry BLOCKED; durable authority is corrupt/ambiguous/lost - explicit operator recovery required")

type mutationKind string

const (
	kMint        mutationKind = "mint_project"
	kEnroll      mutationKind = "enroll_location"
	kSetConsent  mutationKind = "set_consent"
	kIssueGrant  mutationKind = "issue_grant"
	kRevokeGrant mutationKind = "revoke_grant"
	kBarrierProj mutationKind = "delete_project_barrier"
	kBarrierSess mutationKind = "delete_session_barrier"
)

// mutation is the serialized form of one authority change (the WAL payload).
type mutation struct {
	Kind        mutationKind      `json:"kind"`
	UUID        string            `json:"uuid,omitempty"`
	Label       string            `json:"label,omitempty"`
	Loc         registry.Location `json:"loc,omitempty"`
	Confirm     bool              `json:"confirm,omitempty"`
	Project     string            `json:"project,omitempty"`
	Provider    string            `json:"provider,omitempty"`
	Capability  string            `json:"capability,omitempty"`
	Enabled     bool              `json:"enabled,omitempty"`
	Grant       grantDTO          `json:"grant,omitempty"`
	PrincipalID string            `json:"principal_id,omitempty"`
	SessionID   string            `json:"session_id,omitempty"`
	DelEpoch    int64             `json:"del_epoch,omitempty"`
}

// grantDTO is a JSON-safe projection of registry.Grant.
type grantDTO struct {
	PrincipalID string                 `json:"principal_id"`
	Kind        registry.PrincipalKind `json:"kind"`
	Projects    []string               `json:"projects"`
	Ops         []string               `json:"ops"`
	Secret      string                 `json:"secret"`
}

func toDTO(g registry.Grant) grantDTO {
	d := grantDTO{PrincipalID: g.PrincipalID, Kind: g.Kind, Secret: g.Secret}
	for p, ok := range g.Projects {
		if ok {
			d.Projects = append(d.Projects, p)
		}
	}
	for o, ok := range g.Ops {
		if ok {
			d.Ops = append(d.Ops, string(o))
		}
	}
	return d
}

func (d grantDTO) toGrant() registry.Grant {
	g := registry.Grant{PrincipalID: d.PrincipalID, Kind: d.Kind, Secret: d.Secret,
		Projects: map[string]bool{}, Ops: map[registry.Op]bool{}}
	for _, p := range d.Projects {
		g.Projects[p] = true
	}
	for _, o := range d.Ops {
		g.Ops[registry.Op(o)] = true
	}
	return g
}

type metaFile struct {
	Initialized bool   `json:"initialized"`
	HighWater   uint64 `json:"high_water"`
}

// Durable is the durable control registry.
type Durable struct {
	mu          sync.Mutex
	reg         *registry.Registry
	ret         *retention.Manager
	w           *wal.WAL
	lock        *os.File // exclusive cross-process ownership of stateDir (flock), held for lifetime
	stateDir    string
	metaPath    string
	highWater   uint64
	delEpoch    int64
	appendable  bool
	blocked     bool
	blockReason string
}

// opened is the shared result of acquiring exclusive ownership of stateDir, opening the
// WAL and reading the recovery/meta state. Both Open and Initialize build on it.
type opened struct {
	d          *Durable
	recs       []wal.Record
	rep        wal.Report
	meta       metaFile
	metaExists bool
	metaErr    error
}

// prepare acquires exclusive cross-process ownership of stateDir (B: an in-process mutex
// is NOT sufficient; two processes on the same dir would corrupt the WAL), then opens the
// WAL and reads the recovery plan and init marker. The lock is taken BEFORE any WAL/meta
// access, including first-time initialization, and is held for the Durable's lifetime. On
// any error here the lock and WAL are released.
func prepare(stateDir string) (*opened, error) {
	if err := os.MkdirAll(stateDir, 0o700); err != nil {
		return nil, err
	}
	lock, err := acquireLock(stateDir)
	if err != nil {
		return nil, err
	}
	walDir := filepath.Join(stateDir, "wal")
	metaPath := filepath.Join(stateDir, "control.meta")

	reg := registry.New()
	d := &Durable{reg: reg, ret: retention.New(reg), stateDir: stateDir, metaPath: metaPath, lock: lock}

	w, err := wal.Open(walDir)
	if err != nil {
		d.releaseLock()
		return nil, err
	}
	d.w = w

	recs, rep, err := wal.Accepted(walDir)
	if err != nil {
		d.closeAll()
		return nil, err
	}
	meta, metaExists, metaErr := readMeta(metaPath)
	return &opened{d: d, recs: recs, rep: rep, meta: meta, metaExists: metaExists, metaErr: metaErr}, nil
}

// Open opens an EXISTING durable control registry rooted at stateDir. It never
// initializes authority (A): a dir that was never initialized (no marker, no records)
// fails CLOSED (BLOCKED), not a fresh permissive registry, so a mistyped or empty state
// path can never silently become a bypass of the real registry. Explicit first-time
// setup is Initialize. On corrupt/ambiguous/lost durable state Open also returns a BLOCKED
// Durable (not an error), so the server can start, report BLOCKED via /health and deny all
// authority until an operator intervenes. Loss of ALL local evidence is a documented trust
// boundary, not a detectable event.
func Open(stateDir string) (*Durable, error) {
	o, err := prepare(stateDir)
	if err != nil {
		return nil, err
	}
	d := o.d
	switch {
	case o.rep.IsBlocked():
		d.block(fmt.Sprintf("durable authority log is ambiguous/corrupt: %d region(s) preserved for operator resolution", len(o.rep.BlockedDx)))
		return d, nil
	case o.metaErr != nil:
		d.block("control meta marker is present but unreadable/corrupt; operator recovery required")
		return d, nil
	case !o.metaExists:
		if len(o.recs) > 0 {
			d.block("authority log has records but the init marker is missing (inconsistent state); operator recovery required")
			return d, nil
		}
		// NOT first-time init: normal startup must never create authority. Fail closed and
		// require an explicit operator Initialize.
		d.block("control registry is not initialized at this state path; explicit operator initialization is required before any authority is served (refusing silent auto-initialization)")
		return d, nil
	default:
		replayedMax := wal.MaxSeq(o.recs)
		if o.meta.HighWater > replayedMax {
			d.block(fmt.Sprintf("durable authority lost: init high-water %d exceeds recovered max %d; refusing permissive reset - operator recovery required", o.meta.HighWater, replayedMax))
			return d, nil
		}
		// Finalize a clean, provably-unaccepted trailing truncation (never on a blocked log).
		if o.rep.TruncateAt >= 0 {
			if _, err := d.w.Apply(o.rep); err != nil {
				d.closeAll()
				return nil, err
			}
		}
		if err := d.replay(o.recs); err != nil {
			d.closeAll()
			return nil, err
		}
		d.highWater = replayedMax
		if replayedMax != o.meta.HighWater {
			if err := writeMeta(d.metaPath, metaFile{Initialized: true, HighWater: replayedMax}); err != nil {
				d.closeAll()
				return nil, err
			}
		}
		d.appendable = true
		return d, nil
	}
}

// Initialize performs the one explicit operator action that establishes a brand-new
// durable control registry at stateDir. It REFUSES to run against any state that is not
// pristine (A: initialization must never reset existing, partially lost or corrupt state,
// and must never become a recovery bypass): an existing marker, surviving authority
// records, a corrupt/ambiguous log, or an unreadable marker all return an error instead of
// resetting authority. Only a genuinely empty, clean, never-initialized directory is
// initialized. On success it returns an appendable Durable holding the exclusive lock.
func Initialize(stateDir string) (*Durable, error) {
	o, err := prepare(stateDir)
	if err != nil {
		return nil, err
	}
	d := o.d
	switch {
	case o.rep.IsBlocked():
		d.closeAll()
		return nil, fmt.Errorf("control: cannot initialize; existing durable state is corrupt/ambiguous (%d region(s) preserved) - recovery is required, not re-initialization", len(o.rep.BlockedDx))
	case o.metaErr != nil:
		d.closeAll()
		return nil, errors.New("control: cannot initialize; a control meta marker is present but unreadable/corrupt - recovery is required, not re-initialization")
	case o.metaExists:
		d.closeAll()
		return nil, errors.New("control: already initialized; refusing to reset an existing registry (recovery, not initialization, repairs damaged state)")
	case len(o.recs) > 0:
		d.closeAll()
		return nil, errors.New("control: cannot initialize; durable authority records are present without an init marker - recovery is required, refusing a permissive reset that could bypass prior revocations/deletion barriers")
	default:
		if err := writeMeta(d.metaPath, metaFile{Initialized: true, HighWater: 0}); err != nil {
			d.closeAll()
			return nil, err
		}
		d.appendable = true
		return d, nil
	}
}

// acquireLock takes an exclusive, non-blocking advisory lock on stateDir/state.lock and
// returns the held handle. The lockfile is intentionally NOT unlinked on release, so the
// same inode is reused across restarts and a crash cannot leave a half-created lock path;
// the OS drops a flock when the owning process exits (including an abrupt SIGKILL), which
// is exactly how a crashed owner's successor reopens cleanly. Advisory flock is POSIX and
// sufficient for the single-host pilot; it is not a guard against a cooperating process
// that ignores locking.
func acquireLock(stateDir string) (*os.File, error) {
	lockPath := filepath.Join(stateDir, "state.lock")
	f, err := os.OpenFile(lockPath, os.O_CREATE|os.O_RDWR, 0o600)
	if err != nil {
		return nil, err
	}
	if err := syscall.Flock(int(f.Fd()), syscall.LOCK_EX|syscall.LOCK_NB); err != nil {
		f.Close()
		if errors.Is(err, syscall.EWOULDBLOCK) {
			return nil, fmt.Errorf("control: state directory %q is already owned by another running process; exclusive ownership is required (refusing to run concurrently and corrupt the WAL)", stateDir)
		}
		return nil, fmt.Errorf("control: acquiring exclusive state lock on %q: %w", stateDir, err)
	}
	return f, nil
}

func (d *Durable) releaseLock() {
	if d.lock != nil {
		// Explicitly drop the advisory lock, then close the handle (closing would release
		// it anyway). The lockfile is deliberately left on disk.
		_ = syscall.Flock(int(d.lock.Fd()), syscall.LOCK_UN)
		_ = d.lock.Close()
		d.lock = nil
	}
}

// closeAll releases the WAL and the exclusive lock (used on error paths during open).
func (d *Durable) closeAll() {
	if d.w != nil {
		_ = d.w.Close()
	}
	d.releaseLock()
}

func (d *Durable) block(reason string) {
	d.blocked = true
	d.blockReason = reason
	d.appendable = false
}

// Close releases the underlying WAL files and the exclusive state lock, so a successor
// process (or a restart) can reopen the same state directory.
func (d *Durable) Close() error {
	var err error
	if d.w != nil {
		err = d.w.Close()
	}
	d.releaseLock()
	return err
}

// Registry exposes the in-memory authority for authorization checks. When BLOCKED it is
// an empty registry, so authz fails closed (no grants -> denied).
func (d *Durable) Registry() *registry.Registry { return d.reg }

// Retention exposes the deletion-barrier/serve/restore gate.
func (d *Durable) Retention() *retention.Manager { return d.ret }

// Blocked reports whether the durable registry is in the fail-closed BLOCKED state.
func (d *Durable) Blocked() (bool, string) {
	d.mu.Lock()
	defer d.mu.Unlock()
	return d.blocked, d.blockReason
}

// replay reconstructs authority from the ordered accepted records. It applies each
// mutation through the same registry/retention methods (with a synthetic operator
// principal) WITHOUT re-persisting.
func (d *Durable) replay(recs []wal.Record) error {
	op := registry.Principal{ID: "replay", Kind: registry.Operator}
	for _, r := range recs {
		var m mutation
		if err := json.Unmarshal(r.Payload, &m); err != nil {
			return fmt.Errorf("control: corrupt mutation payload at seq %d: %w", r.Seq, err)
		}
		if err := d.apply(op, m); err != nil {
			return fmt.Errorf("control: replay of seq %d (%s) failed: %w", r.Seq, m.Kind, err)
		}
		if m.DelEpoch > d.delEpoch {
			d.delEpoch = m.DelEpoch
		}
	}
	return nil
}

// apply mutates the in-memory registry/retention. It is used by both replay and the live
// mutation methods (ordered relative to persistence per the ordering contract).
func (d *Durable) apply(actor registry.Principal, m mutation) error {
	switch m.Kind {
	case kMint:
		return d.reg.MintProject(actor, m.UUID, m.Label)
	case kEnroll:
		_, err := d.reg.EnrollLocation(actor, m.UUID, m.Loc, m.Confirm)
		return err
	case kSetConsent:
		_, err := d.reg.SetConsent(actor, m.Project, m.Provider, m.Capability, m.Enabled)
		return err
	case kIssueGrant:
		return d.reg.IssueGrant(actor, m.Grant.toGrant())
	case kRevokeGrant:
		return d.reg.RevokeGrant(actor, m.PrincipalID)
	case kBarrierProj:
		d.ret.DeleteProject(m.Project, m.DelEpoch)
		return nil
	case kBarrierSess:
		d.ret.DeleteSession(m.Project, m.SessionID, m.DelEpoch)
		return nil
	default:
		return fmt.Errorf("control: unknown mutation kind %q", m.Kind)
	}
}

// persist writes the mutation to the durable WAL and advances the high-water marker.
// It returns an error if the record could not be durably accepted.
func (d *Durable) persist(m mutation) error {
	payload, err := json.Marshal(m)
	if err != nil {
		return err
	}
	key, err := newKey()
	if err != nil {
		return err
	}
	rcpt, err := d.w.Accept(key, payload)
	if err != nil {
		return err
	}
	// Durably accepted. Advance the marker so a later total loss of the log is detected
	// (meta > recovered max => BLOCKED) rather than mistaken for first-time init.
	if rcpt.Seq > d.highWater {
		d.highWater = rcpt.Seq
		if err := writeMeta(d.metaPath, metaFile{Initialized: true, HighWater: d.highWater}); err != nil {
			return fmt.Errorf("control: record durable (seq %d) but high-water marker update failed: %w", rcpt.Seq, err)
		}
	}
	return nil
}

func (d *Durable) ready() error {
	if d.blocked {
		return ErrBlocked
	}
	if !d.appendable {
		return errors.New("control: registry not appendable (recovery required)")
	}
	return nil
}

// ---- authority-GRANTING mutations: persist BEFORE applying ----

func (d *Durable) MintProject(actor registry.Principal, uuid, label string) error {
	d.mu.Lock()
	defer d.mu.Unlock()
	if err := d.ready(); err != nil {
		return err
	}
	if actor.Kind != registry.Operator {
		return registry.ErrNotOperator
	}
	// D: validate BEFORE persisting. MintProject is authority-granting (persist-then-apply),
	// but registry.MintProject rejects an empty or duplicate UUID only in its apply step. If
	// we persisted first, a rejected mint (dup/empty) would still be a durable record that
	// replay re-applies and fails on - turning a benign HTTP 400 into an UNSTARTABLE server.
	// These checks mirror registry.MintProject exactly and run under the same mutation lock,
	// so a mint that is persisted is one that will also apply cleanly on replay.
	if err := d.validateMint(uuid); err != nil {
		return err
	}
	m := mutation{Kind: kMint, UUID: uuid, Label: label}
	if err := d.persist(m); err != nil {
		return err
	}
	return d.apply(actor, m)
}

// validateMint replicates registry.MintProject's identifier checks (empty/duplicate) so an
// invalid mint is rejected before any durable record is written. Held under d.mu with the
// apply step, the registry state cannot change between this check and apply.
func (d *Durable) validateMint(uuid string) error {
	if uuid == "" {
		return fmt.Errorf("registry: empty project UUID")
	}
	if d.reg.HasProject(uuid) {
		return fmt.Errorf("registry: project already exists")
	}
	return nil
}

func (d *Durable) EnrollLocation(actor registry.Principal, uuid string, loc registry.Location, confirm bool) (registry.LocationStatus, error) {
	d.mu.Lock()
	defer d.mu.Unlock()
	if err := d.ready(); err != nil {
		return "", err
	}
	if actor.Kind != registry.Operator {
		return "", registry.ErrNotOperator
	}
	// A quarantine outcome is not a durable authority change; validate against the live
	// registry first (dry) by attempting on a probe is not possible, so we persist only
	// after a successful apply for enroll - enrollment is bypass-prevention, and a
	// quarantined/rejected enroll must not be journaled as an established location.
	// We therefore apply to a staged check: EnrollLocation is idempotent for an already
	// enrolled match and returns an error for an ambiguous one, so we persist only the
	// mutation that the live apply accepts as enrolled.
	status, err := d.reg.EnrollLocation(actor, uuid, loc, confirm)
	if err != nil {
		return status, err
	}
	m := mutation{Kind: kEnroll, UUID: uuid, Loc: loc, Confirm: confirm}
	if perr := d.persist(m); perr != nil {
		// The live apply happened but is not durable; surface the failure. Enrollment is
		// additive authority - on restart the un-persisted enrollment is simply absent
		// (fail closed), and the operator retries.
		return status, perr
	}
	return status, nil
}

func (d *Durable) SetConsent(actor registry.Principal, project, provider, capability string, enabled bool) (int64, error) {
	d.mu.Lock()
	defer d.mu.Unlock()
	if err := d.ready(); err != nil {
		return 0, err
	}
	if actor.Kind != registry.Operator {
		return 0, registry.ErrNotOperator
	}
	m := mutation{Kind: kSetConsent, Project: project, Provider: provider, Capability: capability, Enabled: enabled}
	if enabled {
		// authority-granting: persist first
		if !d.reg.HasProject(project) {
			return 0, registry.ErrUnknownProj
		}
		if err := d.persist(m); err != nil {
			return 0, err
		}
		return d.reg.SetConsent(actor, project, provider, capability, true)
	}
	// authority-reducing (revoke): apply first (immediate), then persist
	epoch, err := d.reg.SetConsent(actor, project, provider, capability, false)
	if err != nil {
		return 0, err
	}
	if perr := d.persist(m); perr != nil {
		return epoch, perr // in-memory stays revoked (safe); not acknowledged
	}
	return epoch, nil
}

func (d *Durable) IssueGrant(actor registry.Principal, g registry.Grant) error {
	d.mu.Lock()
	defer d.mu.Unlock()
	if err := d.ready(); err != nil {
		return err
	}
	if actor.Kind != registry.Operator {
		return registry.ErrNotOperator
	}
	// D: validate BEFORE persisting, using the registry's OWN single-source-of-truth
	// validator (not a partial copy). A grant that registry.IssueGrant would reject - an
	// unknown op, a bad principal kind, an operator-only op on an agent - must never become
	// a durable record, or replay would fail and the server would be unstartable on restart.
	if err := registry.ValidateGrant(g); err != nil {
		return err
	}
	m := mutation{Kind: kIssueGrant, Grant: toDTO(g)}
	if err := d.persist(m); err != nil {
		return err // not applied -> no uncommitted grant exposed
	}
	return d.reg.IssueGrant(actor, g)
}

// ---- authority-REDUCING mutations: apply BEFORE persisting ----

func (d *Durable) RevokeGrant(actor registry.Principal, principalID string) error {
	d.mu.Lock()
	defer d.mu.Unlock()
	if err := d.ready(); err != nil {
		return err
	}
	if actor.Kind != registry.Operator {
		return registry.ErrNotOperator
	}
	if err := d.reg.RevokeGrant(actor, principalID); err != nil {
		return err
	}
	m := mutation{Kind: kRevokeGrant, PrincipalID: principalID}
	if perr := d.persist(m); perr != nil {
		// In-memory grant is already revoked (denied now); report the durability failure
		// so the operator retries. Stale authority is never served after a failed revoke.
		return perr
	}
	return nil
}

func (d *Durable) DeleteProjectBarrier(actor registry.Principal, project string) (retention.Barrier, error) {
	d.mu.Lock()
	defer d.mu.Unlock()
	if err := d.ready(); err != nil {
		return retention.Barrier{}, err
	}
	if actor.Kind != registry.Operator {
		return retention.Barrier{}, registry.ErrNotOperator
	}
	d.delEpoch++
	b := d.ret.DeleteProject(project, d.delEpoch)
	m := mutation{Kind: kBarrierProj, Project: project, DelEpoch: d.delEpoch}
	if perr := d.persist(m); perr != nil {
		return b, perr // barrier active in memory (deny); not acknowledged
	}
	return b, nil
}

func (d *Durable) DeleteSessionBarrier(actor registry.Principal, project, session string) (retention.Barrier, error) {
	d.mu.Lock()
	defer d.mu.Unlock()
	if err := d.ready(); err != nil {
		return retention.Barrier{}, err
	}
	if actor.Kind != registry.Operator {
		return retention.Barrier{}, registry.ErrNotOperator
	}
	d.delEpoch++
	b := d.ret.DeleteSession(project, session, d.delEpoch)
	m := mutation{Kind: kBarrierSess, Project: project, SessionID: session, DelEpoch: d.delEpoch}
	if perr := d.persist(m); perr != nil {
		return b, perr
	}
	return b, nil
}

func newKey() (string, error) {
	b := make([]byte, 16)
	if _, err := rand.Read(b); err != nil {
		return "", err
	}
	return hex.EncodeToString(b), nil
}

// meta marker I/O (atomic: temp + fsync + rename + dir fsync) ----------------

func readMeta(path string) (metaFile, bool, error) {
	b, err := os.ReadFile(path)
	if errors.Is(err, os.ErrNotExist) {
		return metaFile{}, false, nil
	}
	if err != nil {
		return metaFile{}, true, err
	}
	var m metaFile
	if err := json.Unmarshal(b, &m); err != nil {
		return metaFile{}, true, err
	}
	if !m.Initialized {
		return metaFile{}, true, fmt.Errorf("control: meta marker not initialized")
	}
	return m, true, nil
}

func writeMeta(path string, m metaFile) error {
	b, err := json.Marshal(m)
	if err != nil {
		return err
	}
	tmp := path + ".tmp"
	f, err := os.OpenFile(tmp, os.O_CREATE|os.O_TRUNC|os.O_WRONLY, 0o600)
	if err != nil {
		return err
	}
	if _, err := f.Write(b); err != nil {
		f.Close()
		return err
	}
	if err := f.Sync(); err != nil {
		f.Close()
		return err
	}
	if err := f.Close(); err != nil {
		return err
	}
	if err := os.Rename(tmp, path); err != nil {
		return err
	}
	// fsync the directory so the rename is durable.
	dir, err := os.Open(filepath.Dir(path))
	if err != nil {
		return err
	}
	defer dir.Close()
	return dir.Sync()
}
