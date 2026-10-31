//go:build integration

package workflow

import (
	"aifactory.local/storage/internal/budget"
	"aifactory.local/storage/internal/config"
	"aifactory.local/storage/internal/control"
	"aifactory.local/storage/internal/registry"
	"os"
	"os/exec"
	"path/filepath"
	"testing"
)

func TestRealPGVerifiedCutoverRoundTrip(t *testing.T) {
	s := newPG(t)
	p := uniqueProject(t)
	dir := t.TempDir()
	d, e := control.Initialize(filepath.Join(dir, "control"))
	if e != nil {
		t.Fatal(e)
	}
	defer func() { d.Close() }()
	op := registry.Principal{ID: "op", Kind: registry.Operator}
	if e = d.MintProject(op, p, "P"); e != nil {
		t.Fatal(e)
	}
	file := filepath.Join(dir, "workflow.md")
	initial, e := Document([]Task{{ID: "stable-id", Version: 1, Fields: map[string]string{"status": "pending", "title": "Synthetic"}}})
	if e != nil {
		t.Fatal(e)
	}
	if e = os.WriteFile(file, initial, 0600); e != nil {
		t.Fatal(e)
	}
	if _, e = Cutover(d, s, op, p, file, "stale", registry.OwnerPostgres); e == nil {
		t.Fatal("stale source accepted")
	}
	r, e := Cutover(d, s, op, p, file, hashBytes(initial), registry.OwnerPostgres)
	if e != nil {
		t.Fatal(e)
	}
	d.Close()
	d, e = control.Open(filepath.Join(dir, "control"))
	if e != nil {
		t.Fatal(e)
	}
	owner, epoch, _ := d.Registry().WorkflowAuthority(p)
	if owner != registry.OwnerPostgres || epoch != r.NewEpoch {
		t.Fatal(owner, epoch)
	}
	manager := New(d.Registry(), s)
	if e = manager.Write(p, "stable-id", 1, epoch, map[string]string{"status": "done", "title": "Synthetic"}); e != nil {
		t.Fatal(e)
	}
	if _, e = Cutover(d, s, op, p, file, hashBytes(initial), registry.OwnerMarkdown); e != nil {
		t.Fatal(e)
	}
	_, tasks, e := readDocument(file)
	if e != nil {
		t.Fatal(e)
	}
	if len(tasks) != 1 || tasks[0].Version != 2 || tasks[0].Fields["status"] != "done" {
		t.Fatal(tasks)
	}
	d.Close()
	d, e = control.Open(filepath.Join(dir, "control"))
	if e != nil {
		t.Fatal(e)
	}
	owner, epoch, _ = d.Registry().WorkflowAuthority(p)
	if owner != registry.OwnerMarkdown || epoch != 3 {
		t.Fatal(owner, epoch)
	}
	if e = New(d.Registry(), s).Write(p, "stable-id", 2, 2, map[string]string{}); e == nil {
		t.Fatal("stale writer landed after restart")
	}
	// A manually edited generated block cannot be imported or overwrite DB data.
	b, e := os.ReadFile(file)
	if e != nil {
		t.Fatal(e)
	}
	b = append(b, []byte("Human prose must stay separate.\n")...)
	if e = os.WriteFile(file, b, 0600); e != nil {
		t.Fatal(e)
	}
	if _, e = Cutover(d, s, op, p, file, hashBytes(b), registry.OwnerPostgres); e == nil {
		t.Fatal("manual edit accepted")
	}
}

// Exercise the shipped operator entry point, not just the coordinator method.
func TestWorkflowOperatorExecutableRoundTrip(t *testing.T) {
	s := newPG(t)
	p := uniqueProject(t)
	dir := t.TempDir()
	state := filepath.Join(dir, "control")
	d, e := control.Initialize(state)
	if e != nil {
		t.Fatal(e)
	}
	if e = d.MintProject(registry.Principal{ID: "op", Kind: registry.Operator}, p, "P"); e != nil {
		t.Fatal(e)
	}
	d.Close()
	// Explicitly initialize the new shared ledger in this synthetic CLI fixture.
	defaults := config.Default()
	ledger, err := budget.Initialize(filepath.Join(state, "budget.bin"), budget.Policy{LiveCap: defaults.LiveCapBytes, Headroom: defaults.FreeHeadroom}, func() (budget.Sample, error) { return budget.LocalSample(state, defaults.LiveCapBytes) })
	if err != nil {
		t.Fatal(err)
	}
	ledger.Close()

	document, e := Document([]Task{{ID: "cli-task", Version: 1, Fields: map[string]string{"status": "ready"}}})
	if e != nil {
		t.Fatal(e)
	}
	file := filepath.Join(dir, "workflow.md")
	if e = os.WriteFile(file, document, 0600); e != nil {
		t.Fatal(e)
	}
	secret := filepath.Join(dir, "dsn")
	if e = os.WriteFile(secret, []byte(os.Getenv("PG_DSN")), 0600); e != nil {
		t.Fatal(e)
	}
	binary := filepath.Join(dir, "workflow-operator")
	if output, e := exec.Command("go", "build", "-o", binary, "../../cmd/workflow-operator").CombinedOutput(); e != nil {
		t.Fatalf("build: %v %s", e, output)
	}
	for _, to := range []string{"postgres", "markdown"} {
		b, e := os.ReadFile(file)
		if e != nil {
			t.Fatal(e)
		}
		command := exec.Command(binary, "-state", state, "-document", file, "-revision", hashBytes(b), "-to", to, "-dsn-file", secret, "-edits-frozen", p)
		if output, e := command.CombinedOutput(); e != nil {
			t.Fatalf("operator %s: %v %s", to, e, output)
		}
	}
	d, e = control.Open(state)
	if e != nil {
		t.Fatal(e)
	}
	defer d.Close()
	owner, epoch, _ := d.Registry().WorkflowAuthority(p)
	if owner != registry.OwnerMarkdown || epoch != 3 {
		t.Fatal(owner, epoch)
	}
	got, found, e := s.Get(p, "cli-task")
	if e != nil || !found || got.Fields["status"] != "ready" {
		t.Fatal(got, found, e)
	}
	// A wrong pinned revision must fail via the real command with a nonzero exit.
	d.Close()
	if e = exec.Command(binary, "-state", state, "-document", file, "-revision", "wrong", "-to", "postgres", "-dsn-file", secret, "-edits-frozen", p).Run(); e == nil {
		t.Fatal("operator accepted invalid revision")
	}
}
