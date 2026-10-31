package control

import (
	"aifactory.local/storage/internal/registry"
	"errors"
	"os"
	"testing"
)

func TestDurableGrantErrorIsAmbiguousAuthorizedOutcome(t *testing.T) {
	dir := t.TempDir()
	d := mustInit(t, dir)
	d.MintProject(operator(), "p", "p")
	if e := d.IssueGrant(operator(), agentGrant("prior", "p", "synthetic-prior")); e != nil {
		t.Fatal(e)
	}
	if _, e := d.SetConsent(operator(), "p", "synthetic", "capture", true); e != nil {
		t.Fatal(e)
	}
	if e := os.Mkdir(d.metaPath+".tmp", 0700); e != nil {
		t.Fatal(e)
	}
	e := d.IssueGrant(operator(), agentGrant("a", "p", "synthetic"))
	if !errors.Is(e, ErrPersistence) {
		t.Fatal("expected ambiguous durable outcome", e)
	}
	if _, ok := d.Registry().Lookup("a"); ok {
		t.Fatal("failed call exposed unreconciled live grant")
	}
	if blocked, _ := d.Blocked(); !blocked {
		t.Fatal("continued with divergent live/durable authority")
	}
	if _, ok := d.Registry().Lookup("prior"); ok {
		t.Fatal("BLOCKED registry exposed previously loaded grant")
	}
	if d.Registry().HasProject("p") {
		t.Fatal("BLOCKED registry exposed authority")
	}
	if c := d.Registry().ConsentEpoch("p", "synthetic", "capture"); c.Enabled || c.RevokedThrough < 1 {
		t.Fatal("BLOCKED registry admitted replay", c)
	}
	os.Remove(d.metaPath + ".tmp")
	d.Close()
	d = mustOpen(t, dir)
	defer d.Close()
	if _, ok := d.Registry().Lookup("a"); !ok {
		t.Fatal("lost operator-authorized durable grant")
	}
	if e := d.IssueGrant(registry.Principal{Kind: registry.Agent}, agentGrant("evil", "p", "secret")); !errors.Is(e, registry.ErrNotOperator) {
		t.Fatal(e)
	}
	if _, ok := d.Registry().Lookup("evil"); ok {
		t.Fatal("agent escalated")
	}
}
