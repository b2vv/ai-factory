package control

import (
	"aifactory.local/storage/internal/authz"
	"aifactory.local/storage/internal/registry"
	"errors"
	"strings"
	"testing"
)

func TestWorkflowDurableCutoverAndProjectScopedRevocation(t *testing.T) {
	dir := t.TempDir()
	d, e := Initialize(dir)
	if e != nil {
		t.Fatal(e)
	}
	op := registry.Principal{ID: "op", Kind: registry.Operator}
	for _, p := range []string{"a", "b"} {
		if e = d.MintProject(op, p, p); e != nil {
			t.Fatal(e)
		}
	}
	g := registry.Grant{PrincipalID: "agent", Kind: registry.Agent, Projects: map[string]bool{"a": true, "b": true}, Ops: map[registry.Op]bool{registry.OpWorkflowWrite: true}, Secret: "synthetic"}
	if e = d.IssueGrant(op, g); e != nil {
		t.Fatal(e)
	}
	tok := authz.Token{PrincipalID: "agent", Kind: registry.Agent, Epoch: 1, Secret: "synthetic"}
	verify := func() (string, string, error) { return "revision1", strings.Repeat("a", 64), nil }
	r, e := d.CutoverWorkflow(op, "a", registry.OwnerMarkdown, 1, registry.OwnerPostgres, verify)
	if e != nil {
		t.Fatal(e)
	}
	if r.NewEpoch != 2 {
		t.Fatal(r)
	}
	if _, e = d.CutoverWorkflow(op, "a", registry.OwnerPostgres, 2, registry.OwnerMarkdown, func() (string, string, error) { return "", "", errors.New("verification failed") }); e == nil {
		t.Fatal("bad verification accepted")
	}
	if owner, epoch, _ := d.Registry().WorkflowAuthority("a"); owner != registry.OwnerPostgres || epoch != 2 {
		t.Fatal(owner, epoch)
	}
	if _, e = d.CutoverWorkflow(op, "a", registry.OwnerPostgres, 2, registry.OwnerMarkdown, verify); e != nil {
		t.Fatal(e)
	}
	d.Close()
	d, e = Open(dir)
	if e != nil {
		t.Fatal(e)
	}
	defer d.Close()
	if owner, epoch, _ := d.Registry().WorkflowAuthority("a"); owner != registry.OwnerMarkdown || epoch != 3 {
		t.Fatal(owner, epoch)
	}
	if e = authz.Authorize(d.Registry(), tok, "a", registry.OpWorkflowWrite); e == nil {
		t.Fatal("A grant resurrected")
	}
	if e = authz.Authorize(d.Registry(), tok, "b", registry.OpWorkflowWrite); e != nil {
		t.Fatalf("B affected: %v", e)
	}
	if e = d.Registry().FenceWorkflowCommit("a", 2, func() error { t.Fatal("stale writer ran"); return nil }); e == nil {
		t.Fatal("stale writer allowed")
	}
}

func TestPreparedReceiptDoesNotFlipAfterRestart(t *testing.T) {
	dir := t.TempDir()
	d, e := Initialize(dir)
	if e != nil {
		t.Fatal(e)
	}
	op := registry.Principal{ID: "op", Kind: registry.Operator}
	if e = d.MintProject(op, "a", "A"); e != nil {
		t.Fatal(e)
	}
	r := WorkflowReceipt{Project: "a", From: registry.OwnerMarkdown, To: registry.OwnerPostgres, OldEpoch: 1, NewEpoch: 2, SourceRevision: "rev", ExportHash: strings.Repeat("b", 64)}
	if e = d.persist(mutation{Kind: kWorkflowPrepare, Workflow: &r}); e != nil {
		t.Fatal(e)
	}
	d.Close()
	d, e = Open(dir)
	if e != nil {
		t.Fatal(e)
	}
	defer d.Close()
	if owner, epoch, _ := d.Registry().WorkflowAuthority("a"); owner != registry.OwnerMarkdown || epoch != 1 {
		t.Fatal("prepare changed authority", owner, epoch)
	}
	if _, e = d.CutoverWorkflow(op, "a", registry.OwnerMarkdown, 1, registry.OwnerPostgres, func() (string, string, error) { return "rev", strings.Repeat("b", 64), nil }); e != nil {
		t.Fatal(e)
	}
}
