//go:build integration

package workflow

import (
	"os"
	"path/filepath"
	"testing"

	"aifactory.local/storage/internal/control"
	"aifactory.local/storage/internal/registry"
)

func TestMarkdownIndexPreservesAuthorityAndReconcilesDeletion(t *testing.T) {
	pg := newPG(t)
	p := uniqueProject(t)
	d, e := control.Initialize(filepath.Join(t.TempDir(), "state"))
	if e != nil {
		t.Fatal(e)
	}
	defer d.Close()
	op := registry.Principal{ID: "op", Kind: registry.Operator}
	if e = d.MintProject(op, p, p); e != nil {
		t.Fatal(e)
	}
	dir := t.TempDir()
	path := filepath.Join(dir, "structured.md")
	human := filepath.Join(dir, "human.md")
	prose := []byte("# Human notes\nKeep this body byte-for-byte.\n")
	if e = os.WriteFile(human, prose, 0600); e != nil {
		t.Fatal(e)
	}
	tasks := []Task{{ID: "task:one", Version: 1, Fields: map[string]string{"kind": "task", "stage_id": "stage:one"}}, {ID: "stage:one", Version: 1, Fields: map[string]string{"kind": "stage"}}, {ID: "gate:one", Version: 1, Fields: map[string]string{"kind": "gate", "stage_id": "stage:one"}}}
	doc, e := Document(tasks)
	if e != nil {
		t.Fatal(e)
	}
	if e = os.WriteFile(path, doc, 0600); e != nil {
		t.Fatal(e)
	}
	if e = IndexMarkdown(d, pg, op, p, path, hashBytes(doc)); e != nil {
		t.Fatal(e)
	}
	owner, epoch, _ := d.Registry().WorkflowAuthority(p)
	if owner != registry.OwnerMarkdown || epoch != 1 {
		t.Fatalf("index transferred authority: %v %v", owner, epoch)
	}
	if _, ok, e := pg.Get(p, "gate:one"); e != nil || !ok {
		t.Fatalf("index gate: %v %v", ok, e)
	}
	// Rename does not change the stable entity IDs or their source revision.
	renamed := filepath.Join(dir, "renamed.md")
	if e = os.Rename(path, renamed); e != nil {
		t.Fatal(e)
	}
	if e = IndexMarkdown(d, pg, op, p, renamed, hashBytes(doc)); e != nil {
		t.Fatal(e)
	}
	next, e := Document(tasks[:2])
	if e != nil {
		t.Fatal(e)
	}
	if e = os.WriteFile(renamed, next, 0600); e != nil {
		t.Fatal(e)
	}
	if e = IndexMarkdown(d, pg, op, p, renamed, hashBytes(doc)); e == nil {
		t.Fatal("stale source revision accepted")
	}
	if e = IndexMarkdown(d, pg, op, p, renamed, hashBytes(next)); e != nil {
		t.Fatal(e)
	}
	if _, ok, e := pg.Get(p, "gate:one"); e != nil || ok {
		t.Fatalf("deleted entity remains: %v %v", ok, e)
	}
	if e = os.WriteFile(renamed, append(next, []byte("manual edit")...), 0600); e != nil {
		t.Fatal(e)
	}
	if e = IndexMarkdown(d, pg, op, p, renamed, hashBytes(next)); e == nil {
		t.Fatal("manual projection edit accepted")
	}
	got, e := os.ReadFile(human)
	if e != nil || string(got) != string(prose) {
		t.Fatalf("human prose changed: %v", e)
	}
}
