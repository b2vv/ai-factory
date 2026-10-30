package control

import (
	"os"
	"path/filepath"
	"testing"

	"aifactory.local/storage/internal/archive"
	"aifactory.local/storage/internal/authz"
	"aifactory.local/storage/internal/registry"
)

func operator() registry.Principal { return registry.Principal{ID: "op", Kind: registry.Operator} }

func agentGrant(principal, project, secret string) registry.Grant {
	return registry.Grant{
		PrincipalID: principal,
		Kind:        registry.Agent,
		Projects:    map[string]bool{project: true},
		Ops:         map[registry.Op]bool{registry.OpArchiveQuery: true},
		Secret:      secret,
	}
}

func mustOpen(t *testing.T, dir string) *Durable {
	t.Helper()
	d, err := Open(dir)
	if err != nil {
		t.Fatalf("Open: %v", err)
	}
	return d
}

// mustInit performs the explicit first-time initialization (A). Normal Open no longer
// auto-initializes, so every test that starts from a pristine dir initializes first.
func mustInit(t *testing.T, dir string) *Durable {
	t.Helper()
	d, err := Initialize(dir)
	if err != nil {
		t.Fatalf("Initialize: %v", err)
	}
	return d
}

// seed enrolls a project and issues an agent grant; returns the token the agent holds.
func seed(t *testing.T, d *Durable, project, principal, secret string) authz.Token {
	t.Helper()
	if err := d.MintProject(operator(), project, "label"); err != nil {
		t.Fatalf("MintProject: %v", err)
	}
	if err := d.IssueGrant(operator(), agentGrant(principal, project, secret)); err != nil {
		t.Fatalf("IssueGrant: %v", err)
	}
	g, ok := d.Registry().Lookup(principal)
	if !ok {
		t.Fatalf("grant not found after issue")
	}
	return authz.Token{PrincipalID: principal, Kind: registry.Agent, Epoch: g.Epoch, Secret: secret}
}

func TestFirstTimeInit_NotBlocked_And_RestartStaysEmpty(t *testing.T) {
	dir := t.TempDir()
	d := mustInit(t, dir)
	if b, _ := d.Blocked(); b {
		t.Fatalf("fresh init must not be blocked")
	}
	d.Close()
	d2 := mustOpen(t, dir)
	defer d2.Close()
	if b, r := d2.Blocked(); b {
		t.Fatalf("empty initialized registry must reopen clean, got blocked: %s", r)
	}
	if len(d2.Registry().Projects()) != 0 {
		t.Fatalf("expected empty registry after reopen")
	}
}

func TestRevokedGrantRemainsRejectedAfterRestart(t *testing.T) {
	dir := t.TempDir()
	d := mustInit(t, dir)
	tok := seed(t, d, "proj-A", "agent-1", "s3cret")
	// Before revoke: authorized.
	if err := authz.Authorize(d.Registry(), tok, "proj-A", registry.OpArchiveQuery); err != nil {
		t.Fatalf("expected authorized before revoke: %v", err)
	}
	if err := d.RevokeGrant(operator(), "agent-1"); err != nil {
		t.Fatalf("RevokeGrant: %v", err)
	}
	d.Close()

	// Restart: the revocation MUST survive.
	d2 := mustOpen(t, dir)
	defer d2.Close()
	if b, r := d2.Blocked(); b {
		t.Fatalf("unexpected blocked: %s", r)
	}
	if err := authz.Authorize(d2.Registry(), tok, "proj-A", registry.OpArchiveQuery); err == nil {
		t.Fatalf("revoked grant must stay rejected after restart")
	}
}

func TestValidGrantPersistsAcrossRestart(t *testing.T) {
	dir := t.TempDir()
	d := mustInit(t, dir)
	tok := seed(t, d, "proj-A", "agent-1", "s3cret")
	d.Close()
	d2 := mustOpen(t, dir)
	defer d2.Close()
	if err := authz.Authorize(d2.Registry(), tok, "proj-A", registry.OpArchiveQuery); err != nil {
		t.Fatalf("valid grant must persist across restart: %v", err)
	}
}

func TestDeletionBarrierPersistsAcrossRestart(t *testing.T) {
	dir := t.TempDir()
	d := mustInit(t, dir)
	if err := d.MintProject(operator(), "proj-A", "l"); err != nil {
		t.Fatalf("mint: %v", err)
	}
	if _, err := d.DeleteProjectBarrier(operator(), "proj-A"); err != nil {
		t.Fatalf("barrier: %v", err)
	}
	d.Close()

	d2 := mustOpen(t, dir)
	defer d2.Close()
	rec := archive.Record{Project: "proj-A", Provider: "x", SessionID: "s1"}
	served := d2.Retention().Serve([]archive.Record{rec}, "capture")
	if len(served) != 0 {
		t.Fatalf("deletion barrier must persist: record for barred project was served")
	}
}

func TestConsentRevocationPersistsAcrossRestart(t *testing.T) {
	dir := t.TempDir()
	d := mustInit(t, dir)
	if err := d.MintProject(operator(), "proj-A", "l"); err != nil {
		t.Fatalf("mint: %v", err)
	}
	if _, err := d.SetConsent(operator(), "proj-A", "prov", "capture", true); err != nil {
		t.Fatalf("consent enable: %v", err)
	}
	if _, err := d.SetConsent(operator(), "proj-A", "prov", "capture", false); err != nil {
		t.Fatalf("consent revoke: %v", err)
	}
	d.Close()

	d2 := mustOpen(t, dir)
	defer d2.Close()
	c := d2.Registry().ConsentEpoch("proj-A", "prov", "capture")
	if c.Enabled {
		t.Fatalf("consent revocation must persist as disabled after restart")
	}
	if c.Epoch != 2 {
		t.Fatalf("expected consent epoch 2 after enable+revoke, got %d", c.Epoch)
	}
}

func TestCorruptWALFailsClosedNotPermissive(t *testing.T) {
	dir := t.TempDir()
	d := mustInit(t, dir)
	tok := seed(t, d, "proj-A", "agent-1", "s3cret")
	_ = tok
	d.Close()

	// Corrupt the WAL data file (flip bytes in an accepted frame payload).
	dataPath := filepath.Join(dir, "wal", "data")
	b, err := os.ReadFile(dataPath)
	if err != nil || len(b) < 4 {
		t.Fatalf("read wal data: %v (len %d)", err, len(b))
	}
	b[len(b)-5] ^= 0xFF // corrupt within the last accepted frame
	if err := os.WriteFile(dataPath, b, 0o600); err != nil {
		t.Fatalf("write corrupt data: %v", err)
	}

	d2 := mustOpen(t, dir)
	defer d2.Close()
	blocked, reason := d2.Blocked()
	if !blocked {
		t.Fatalf("corrupt WAL must fail closed (BLOCKED), got not-blocked")
	}
	if reason == "" {
		t.Fatalf("blocked reason must be actionable")
	}
	// Must not be a permissive reset: authority is denied and mutations are refused.
	if err := authz.Authorize(d2.Registry(), authz.Token{PrincipalID: "agent-1", Kind: registry.Agent, Epoch: 1, Secret: "s3cret"}, "proj-A", registry.OpArchiveQuery); err == nil {
		t.Fatalf("blocked registry must deny all authority")
	}
	if err := d2.MintProject(operator(), "proj-B", "l"); err != ErrBlocked {
		t.Fatalf("blocked registry must refuse mutations with ErrBlocked, got %v", err)
	}
}

func TestLostLogFailsClosedNotPermissive(t *testing.T) {
	dir := t.TempDir()
	d := mustInit(t, dir)
	if err := d.MintProject(operator(), "proj-A", "l"); err != nil {
		t.Fatalf("mint: %v", err)
	}
	if err := d.RevokeGrant(operator(), "nobody"); err == nil {
		// not relevant; ignore (no such grant). Keep at least one real mutation (mint) above.
	}
	d.Close()

	// Simulate the WAL files being lost while the init marker survives.
	walDir := filepath.Join(dir, "wal")
	for _, name := range []string{"data", "intents", "accepts", "committed.idx"} {
		_ = os.Remove(filepath.Join(walDir, name))
	}

	d2 := mustOpen(t, dir)
	defer d2.Close()
	if b, _ := d2.Blocked(); !b {
		t.Fatalf("lost authority log with surviving init marker must fail closed, not re-init permissively")
	}
	if len(d2.Registry().Projects()) != 0 {
		t.Fatalf("blocked registry must not expose any reconstructed authority")
	}
}

func TestMissingMetaWithRecordsIsBlocked(t *testing.T) {
	dir := t.TempDir()
	d := mustInit(t, dir)
	if err := d.MintProject(operator(), "proj-A", "l"); err != nil {
		t.Fatalf("mint: %v", err)
	}
	d.Close()
	// Remove the init marker but keep the records: inconsistent -> must block.
	if err := os.Remove(filepath.Join(dir, "control.meta")); err != nil {
		t.Fatalf("rm meta: %v", err)
	}
	d2 := mustOpen(t, dir)
	defer d2.Close()
	if b, _ := d2.Blocked(); !b {
		t.Fatalf("records without an init marker must fail closed")
	}
}

func TestIssueGrantPersistFailureNotExposed(t *testing.T) {
	dir := t.TempDir()
	d := mustInit(t, dir)
	if err := d.MintProject(operator(), "proj-A", "l"); err != nil {
		t.Fatalf("mint: %v", err)
	}
	// Force a real durability failure by closing the WAL fds; the next Accept write fails
	// BEFORE any durable boundary, so the grant must never be applied/exposed.
	d.w.Close()
	err := d.IssueGrant(operator(), agentGrant("agent-1", "proj-A", "s"))
	if err == nil {
		t.Fatalf("expected IssueGrant to fail when persistence fails")
	}
	if _, ok := d.Registry().Lookup("agent-1"); ok {
		t.Fatalf("uncommitted grant must NOT be exposed after a persistence failure")
	}
}

func TestRevokePersistFailureStaysDenied(t *testing.T) {
	dir := t.TempDir()
	d := mustInit(t, dir)
	tok := seed(t, d, "proj-A", "agent-1", "s3cret")
	if err := authz.Authorize(d.Registry(), tok, "proj-A", registry.OpArchiveQuery); err != nil {
		t.Fatalf("precondition: authorized, got %v", err)
	}
	// Force durability failure, then revoke: in-memory must become denied even though the
	// revoke could not be acknowledged (no stale authority served after a failed revoke).
	d.w.Close()
	if err := d.RevokeGrant(operator(), "agent-1"); err == nil {
		t.Fatalf("expected RevokeGrant to report the persistence failure")
	}
	if err := authz.Authorize(d.Registry(), tok, "proj-A", registry.OpArchiveQuery); err == nil {
		t.Fatalf("after a failed revoke the grant must be denied in-memory, not served stale")
	}
}

// D: a rejected mint (duplicate or empty UUID) must leave NO durable record, so a restart
// replays cleanly instead of re-applying a poison record and becoming unstartable.
func TestMintValidationLeavesNoPoisonRecord(t *testing.T) {
	dir := t.TempDir()
	d := mustInit(t, dir)
	if err := d.MintProject(operator(), "proj-A", "l"); err != nil {
		t.Fatalf("first mint: %v", err)
	}
	if err := d.MintProject(operator(), "proj-A", "l"); err == nil {
		t.Fatalf("duplicate mint must be rejected")
	}
	if err := d.MintProject(operator(), "", "l"); err == nil {
		t.Fatalf("empty-UUID mint must be rejected")
	}
	d.Close()

	// Restart: the rejected mints must not have been journaled. A poison record would make
	// replay fail and Open return BLOCKED (or, pre-fix, an unstartable error).
	d2 := mustOpen(t, dir)
	defer d2.Close()
	if b, r := d2.Blocked(); b {
		t.Fatalf("restart after rejected mints must be healthy, got blocked: %s", r)
	}
	if n := len(d2.Registry().Projects()); n != 1 {
		t.Fatalf("exactly one project must be durable after rejected mints, got %d", n)
	}
}

// D (sibling path): a grant that the registry would reject (here, an unknown op) must be
// refused BEFORE any durable record is written, so a restart replays cleanly instead of
// re-applying a poison grant record and becoming unstartable.
func TestIssueGrantValidationLeavesNoPoisonRecord(t *testing.T) {
	dir := t.TempDir()
	d := mustInit(t, dir)
	if err := d.MintProject(operator(), "proj-A", "l"); err != nil {
		t.Fatalf("mint: %v", err)
	}
	// Unknown op (a plausible shorthand/typo) — rejected by registry.ValidateGrant.
	bad := registry.Grant{
		PrincipalID: "agent-1",
		Kind:        registry.Agent,
		Projects:    map[string]bool{"proj-A": true},
		Ops:         map[registry.Op]bool{registry.Op("read"): true},
		Secret:      "s",
	}
	if err := d.IssueGrant(operator(), bad); err == nil {
		t.Fatalf("grant with an unknown op must be rejected")
	}
	// A valid grant afterwards must still work (the registry is not wedged).
	if err := d.IssueGrant(operator(), agentGrant("agent-2", "proj-A", "s")); err != nil {
		t.Fatalf("valid grant after a rejected one: %v", err)
	}
	d.Close()

	// Restart: the rejected grant must not have been journaled; a poison record would make
	// replay fail and the server unstartable.
	d2 := mustOpen(t, dir)
	defer d2.Close()
	if b, r := d2.Blocked(); b {
		t.Fatalf("restart after a rejected grant must be healthy, got blocked: %s", r)
	}
	if _, ok := d2.Registry().Lookup("agent-1"); ok {
		t.Fatalf("rejected grant must not be durable after restart")
	}
	if _, ok := d2.Registry().Lookup("agent-2"); !ok {
		t.Fatalf("the valid grant must be durable after restart")
	}
}

// A: normal Open must never initialize authority. An uninitialized (or mistyped) state path
// fails closed, not into a fresh permissive registry.
func TestOpenUninitializedFailsClosed(t *testing.T) {
	dir := t.TempDir()
	d, err := Open(dir) // never Initialize'd
	if err != nil {
		t.Fatalf("Open: %v", err)
	}
	defer d.Close()
	if b, _ := d.Blocked(); !b {
		t.Fatalf("Open on an uninitialized dir must fail closed (BLOCKED), not auto-initialize")
	}
	if err := d.MintProject(operator(), "p", "l"); err != ErrBlocked {
		t.Fatalf("uninitialized registry must refuse mutations with ErrBlocked, got %v", err)
	}
}

// A: Initialize must refuse to reset an already-initialized registry.
func TestInitializeRefusesExistingRegistry(t *testing.T) {
	dir := t.TempDir()
	mustInit(t, dir).Close()
	if _, err := Initialize(dir); err == nil {
		t.Fatalf("Initialize on an already-initialized dir must be refused")
	}
}

// A: Initialize must refuse surviving authority records with a lost marker, rather than
// reset to a permissive empty registry (which would bypass prior revocations/barriers).
func TestInitializeRefusesRecordsWithoutMarker(t *testing.T) {
	dir := t.TempDir()
	d := mustInit(t, dir)
	if err := d.MintProject(operator(), "proj-A", "l"); err != nil {
		t.Fatalf("mint: %v", err)
	}
	d.Close()
	if err := os.Remove(filepath.Join(dir, "control.meta")); err != nil {
		t.Fatalf("rm meta: %v", err)
	}
	if _, err := Initialize(dir); err == nil {
		t.Fatalf("Initialize must refuse a dir that still holds authority records (recovery bypass guard)")
	}
}

// A: Initialize must refuse a corrupt/ambiguous log (recovery is required, not re-init).
func TestInitializeRefusesCorruptLog(t *testing.T) {
	dir := t.TempDir()
	d := mustInit(t, dir)
	if err := d.MintProject(operator(), "proj-A", "l"); err != nil {
		t.Fatalf("mint: %v", err)
	}
	d.Close()
	dataPath := filepath.Join(dir, "wal", "data")
	b, err := os.ReadFile(dataPath)
	if err != nil || len(b) < 6 {
		t.Fatalf("read wal data: %v len %d", err, len(b))
	}
	b[len(b)-5] ^= 0xFF
	if err := os.WriteFile(dataPath, b, 0o600); err != nil {
		t.Fatalf("write corrupt data: %v", err)
	}
	if _, err := Initialize(dir); err == nil {
		t.Fatalf("Initialize must refuse a corrupt/ambiguous log")
	}
}

// B: exclusive ownership within a single process (a distinct open file description still
// contends on the flock). The cross-process cases are covered by cmd/factory's smoke tests.
func TestExclusiveLockRejectsConcurrentOpen(t *testing.T) {
	dir := t.TempDir()
	d := mustInit(t, dir)
	if _, err := Open(dir); err == nil {
		d.Close()
		t.Fatalf("a second Open while the first holds the exclusive lock must fail")
	}
	d.Close()
	// After release, the same dir reopens.
	d2, err := Open(dir)
	if err != nil {
		t.Fatalf("reopen after close must succeed: %v", err)
	}
	d2.Close()
}

func TestMutationsAreOperatorOnly(t *testing.T) {
	dir := t.TempDir()
	d := mustInit(t, dir)
	defer d.Close()
	ag := registry.Principal{ID: "agent-1", Kind: registry.Agent}
	if err := d.MintProject(ag, "proj-A", "l"); err != registry.ErrNotOperator {
		t.Fatalf("agent MintProject must be rejected, got %v", err)
	}
	if err := d.IssueGrant(ag, agentGrant("agent-2", "proj-A", "s")); err != registry.ErrNotOperator {
		t.Fatalf("agent IssueGrant must be rejected, got %v", err)
	}
}
