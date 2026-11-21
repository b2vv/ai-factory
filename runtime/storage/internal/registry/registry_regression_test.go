package registry

// Regression tests for interim-review finding IR5: returned/accepted grant maps must
// not alias stored authority, and a quarantined location must not self-resolve on a
// bare retry.

import "testing"

func operator() Principal { return Principal{ID: "op-1", Kind: Operator} }

// IR5a — Lookup must return a deep copy. Mutating the returned Projects/Ops maps must
// not change stored authorization (which would bypass the operator check and epoch
// bump). Reviewer evidence (lookup_mutates_grant_without_operator): delete=true,
// foreign_project=true were observable on a later Lookup on the buggy tree.
func TestIR5_LookupGrantIsNotAliased(t *testing.T) {
	r := New()
	if err := r.MintProject(operator(), "proj-A", "A"); err != nil {
		t.Fatal(err)
	}
	g := Grant{
		PrincipalID: "agent-1",
		Kind:        Agent,
		Projects:    map[string]bool{"proj-A": true},
		Ops:         map[Op]bool{OpCapture: true},
		Secret:      "s",
	}
	if err := r.IssueGrant(operator(), g); err != nil {
		t.Fatal(err)
	}

	// Mutate the external map the caller handed us: stored state must be unaffected.
	g.Ops[OpDelete] = true
	g.Projects["foreign-project"] = true

	got, ok := r.Lookup("agent-1")
	if !ok {
		t.Fatal("grant missing")
	}
	if got.Ops[OpDelete] {
		t.Fatalf("IR5: caller-owned map aliased stored grant; operator-only op leaked in")
	}
	if got.Projects["foreign-project"] {
		t.Fatalf("IR5: caller-owned map aliased stored grant; foreign project leaked in")
	}

	// Mutate the map returned BY Lookup: a second Lookup must still be clean.
	got.Ops[OpDelete] = true
	got.Projects["foreign-project"] = true
	again, _ := r.Lookup("agent-1")
	if again.Ops[OpDelete] || again.Projects["foreign-project"] {
		t.Fatalf("IR5: Lookup returned an aliased map; mutation outside operator checks persisted")
	}
}

// IR5b — a quarantined location must require explicit operator resolution; repeating
// the same ambiguous enrollment with confirmSameProject=false must NOT upgrade it to
// enrolled. Reviewer: "Explicit resolution can therefore be bypassed by retry."
func TestIR5_QuarantineDoesNotSelfResolveOnRetry(t *testing.T) {
	r := New()
	if err := r.MintProject(operator(), "proj-A", "A"); err != nil {
		t.Fatal(err)
	}
	// First location enrolls cleanly.
	if st, err := r.EnrollLocation(operator(), "proj-A", Location{MachineID: "m1", GitRootResolved: "/root/a"}, false); err != nil || st != LocEnrolled {
		t.Fatalf("first enroll: st=%v err=%v", st, err)
	}
	// A second, unrelated checkout carrying the same UUID is ambiguous -> quarantine.
	amb := Location{MachineID: "m2", GitRootResolved: "/root/b"}
	st, err := r.EnrollLocation(operator(), "proj-A", amb, false)
	if st != LocQuarantined || err != ErrDupUUID {
		t.Fatalf("expected quarantine on ambiguous enroll: st=%v err=%v", st, err)
	}
	// Bare retry of the exact same ambiguous request must stay quarantined.
	st2, err2 := r.EnrollLocation(operator(), "proj-A", amb, false)
	if st2 != LocQuarantined || err2 != ErrDupUUID {
		t.Fatalf("IR5: quarantine self-resolved on retry: st=%v err=%v", st2, err2)
	}
}
