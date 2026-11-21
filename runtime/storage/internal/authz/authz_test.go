package authz

import (
	"testing"

	"aifactory.local/storage/internal/registry"
)

// setup mints two projects and issues an agent grant scoped to proj-A / archive.query.
func setup(t *testing.T) (*registry.Registry, Token) {
	t.Helper()
	reg := registry.New()
	op := registry.Principal{ID: "op", Kind: registry.Operator}
	for _, p := range []string{"proj-A", "proj-B"} {
		if err := reg.MintProject(op, p, "l"); err != nil {
			t.Fatalf("mint %s: %v", p, err)
		}
	}
	g := registry.Grant{
		PrincipalID: "agent-1",
		Kind:        registry.Agent,
		Projects:    map[string]bool{"proj-A": true},
		Ops:         map[registry.Op]bool{registry.OpArchiveQuery: true},
		Secret:      "sek",
	}
	if err := reg.IssueGrant(op, g); err != nil {
		t.Fatalf("issue: %v", err)
	}
	stored, _ := reg.Lookup("agent-1")
	return reg, Token{PrincipalID: "agent-1", Kind: registry.Agent, Epoch: stored.Epoch, Secret: "sek"}
}

func TestAuthorizeGranted(t *testing.T) {
	reg, tok := setup(t)
	if err := Authorize(reg, tok, "proj-A", registry.OpArchiveQuery); err != nil {
		t.Fatalf("granted request must pass: %v", err)
	}
}

func TestCrossProjectDenied(t *testing.T) { // P10
	reg, tok := setup(t)
	if err := Authorize(reg, tok, "proj-B", registry.OpArchiveQuery); err != ErrProjectDenied {
		t.Fatalf("project-A token must be denied project B, got %v", err)
	}
}

func TestOpOutsideGrantDenied(t *testing.T) { // P10
	reg, tok := setup(t)
	if err := Authorize(reg, tok, "proj-A", registry.OpWorkflowWrite); err != ErrOpDenied {
		t.Fatalf("op outside the grant must be denied, got %v", err)
	}
}

func TestBadSecretDenied(t *testing.T) {
	reg, tok := setup(t)
	tok.Secret = "wrong"
	if err := Authorize(reg, tok, "proj-A", registry.OpArchiveQuery); err != ErrBadSecret {
		t.Fatalf("bad secret must be denied, got %v", err)
	}
}

func TestStaleEpochDeniedAfterRevoke(t *testing.T) { // P10/P11
	reg, tok := setup(t)
	op := registry.Principal{ID: "op", Kind: registry.Operator}
	if err := reg.RevokeGrant(op, "agent-1"); err != nil {
		t.Fatalf("revoke: %v", err)
	}
	if err := Authorize(reg, tok, "proj-A", registry.OpArchiveQuery); err != ErrStaleGrant {
		t.Fatalf("token for a revoked grant must be stale/denied, got %v", err)
	}
}

func TestAgentCannotActCrossProject(t *testing.T) { // P11/P14
	reg, tok := setup(t)
	if err := AuthorizeCrossProject(reg, tok, registry.OpSearch); err != ErrCrossProject {
		t.Fatalf("agent must not hold cross-project authority, got %v", err)
	}
}

func TestNoGrantDenied(t *testing.T) {
	reg, _ := setup(t)
	tok := Token{PrincipalID: "ghost", Kind: registry.Agent, Epoch: 1, Secret: "x"}
	if err := Authorize(reg, tok, "proj-A", registry.OpArchiveQuery); err != ErrNoGrant {
		t.Fatalf("unknown principal must be denied, got %v", err)
	}
}
