// Package authz enforces access in the trusted API (R4). A supplied project UUID is
// NEVER authorization by itself. Every request presents a principal-bound Token;
// authorization requires that the principal has a current (non-revoked, non-stale)
// grant covering BOTH the requested project AND the requested operation. Cross-
// project access requires an operator principal holding the cross_project op.
package authz

import (
	"errors"

	"aifactory.local/storage/internal/registry"
)

// Token is presented with each request. Secret is matched against the stored grant
// secret; Epoch pins the grant version the token was issued for, so a later
// revocation or re-issue (which bumps the registry epoch) makes this token stale.
type Token struct {
	PrincipalID string
	Kind        registry.PrincipalKind
	Epoch       int64
	Secret      string
}

var (
	ErrNoGrant       = errors.New("authz: no grant for principal")
	ErrStaleGrant    = errors.New("authz: stale or revoked grant (epoch mismatch)")
	ErrBadSecret     = errors.New("authz: token secret mismatch")
	ErrProjectDenied = errors.New("authz: principal not granted the requested project")
	ErrOpDenied      = errors.New("authz: principal not granted the requested operation")
	ErrCrossProject  = errors.New("authz: cross-project access requires operator with cross_project op")
)

// Authorize checks a single (project, op) request. It is the only entry agents use;
// it fails closed on any mismatch.
func Authorize(reg *registry.Registry, tok Token, project string, op registry.Op) error {
	g, ok := reg.Lookup(tok.PrincipalID)
	if !ok {
		return ErrNoGrant
	}
	if g.Revoked || g.Epoch != tok.Epoch {
		return ErrStaleGrant
	}
	if g.Secret != tok.Secret {
		return ErrBadSecret
	}
	if !g.Ops[op] {
		return ErrOpDenied
	}
	if !g.Projects[project] {
		return ErrProjectDenied
	}
	return nil
}

// AuthorizeCrossProject checks a cross-project operation (e.g. cross-project search).
// It requires an operator principal holding OpCrossProject and the specific op.
func AuthorizeCrossProject(reg *registry.Registry, tok Token, op registry.Op) error {
	g, ok := reg.Lookup(tok.PrincipalID)
	if !ok {
		return ErrNoGrant
	}
	if g.Revoked || g.Epoch != tok.Epoch {
		return ErrStaleGrant
	}
	if g.Secret != tok.Secret {
		return ErrBadSecret
	}
	if g.Kind != registry.Operator || !g.Ops[registry.OpCrossProject] || !g.Ops[op] {
		return ErrCrossProject
	}
	return nil
}
