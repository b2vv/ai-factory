//go:build integration

package search

import (
	"aifactory.local/storage/internal/budget"
	"aifactory.local/storage/internal/config"
	"aifactory.local/storage/internal/control"
	"aifactory.local/storage/internal/registry"
	"bytes"
	"encoding/json"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"testing"
	"time"
)

func TestDocumentOperatorRealPGStableProvenanceTombstoneAndRebuild(t *testing.T) {
	s := realStore(t)
	project := fmt.Sprintf("docs_%d", time.Now().UnixNano())
	defer s.Purge(project)
	root := t.TempDir()
	state := filepath.Join(root, "state")
	d, e := control.Initialize(state)
	if e != nil {
		t.Fatal(e)
	}
	if e = d.MintProject(registry.Principal{ID: "op", Kind: registry.Operator}, project, project); e != nil {
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

	dsn := filepath.Join(root, "dsn")
	if e = os.WriteFile(dsn, []byte(os.Getenv("PG_DSN")), 0600); e != nil {
		t.Fatal(e)
	}
	bin := filepath.Join(root, "document-operator")
	build := exec.Command("go", "build", "-o", bin, "../../cmd/document-operator")
	if out, e := build.CombinedOutput(); e != nil {
		t.Fatalf("build %v: %s", e, out)
	}
	call := func(operation, path, expected string, wantSuccess bool) string {
		t.Helper()
		payload, _ := json.Marshal(map[string]string{"Operation": operation, "Project": project, "Root": root, "Ledger": "ledger.md", "ID": "stable-doc", "Path": path, "ExpectedRevision": expected})
		command := exec.Command(bin, "-state", state, "-dsn-file", dsn, "-exclusive-window")
		command.Stdin = bytes.NewReader(payload)
		out, e := command.CombinedOutput()
		if (e == nil) != wantSuccess {
			t.Fatalf("operation %s error=%v output=%s", operation, e, out)
		}
		if e != nil {
			return ""
		}
		var result map[string]any
		if e = json.Unmarshal(out, &result); e != nil {
			t.Fatal(e)
		}
		return result["revision"].(string)
	}
	original := []byte("<!-- factory-document-id: \"stable-doc\" -->\n# Human Markdown\nSynthetic text preserved.\n")
	old := filepath.Join(root, "old.md")
	if e = os.WriteFile(old, original, 0600); e != nil {
		t.Fatal(e)
	}
	revision := call("upsert", "old.md", "", true)
	call("index", "", revision, true)
	rows, _, e := s.DocumentWindow(project, "")
	if e != nil || len(rows) != 1 || rows[0].ID != "stable-doc" || rows[0].Path != "old.md" {
		t.Fatal(rows, e)
	}
	if e = ValidateDocument(rows[0]); e != nil {
		t.Fatal(e)
	}
	if e = os.Rename(old, filepath.Join(root, "new.md")); e != nil {
		t.Fatal(e)
	}
	revision = call("upsert", "new.md", revision, true)
	if e = ValidateDocument(rows[0]); e == nil {
		t.Fatal("stale path served after rename")
	}
	call("index", "", revision, true)
	rows, _, e = s.DocumentWindow(project, "")
	if e != nil || len(rows) != 1 || rows[0].ID != "stable-doc" || rows[0].Version != 2 {
		t.Fatal(rows, e)
	}
	if e = ValidateDocument(rows[0]); e != nil {
		t.Fatal(e)
	}
	if b, e := os.ReadFile(filepath.Join(root, "new.md")); e != nil || !bytes.Equal(b, original) {
		t.Fatal("human prose changed", e)
	}
	call("upsert", "new.md", "stale", false)
	if e = os.Remove(filepath.Join(root, "new.md")); e != nil {
		t.Fatal(e)
	}
	revision = call("delete", "new.md", revision, true)
	if e = ValidateDocument(rows[0]); e == nil {
		t.Fatal("deleted source served from stale index")
	}
	call("index", "", revision, true)
	rows, _, e = s.DocumentWindow(project, "")
	if e != nil || len(rows) != 1 || !rows[0].Deleted || rows[0].Version != 3 {
		t.Fatal(rows, e)
	}
	before := rows[0]
	if e = s.Purge(project); e != nil {
		t.Fatal(e)
	}
	call("index", "", revision, true)
	rows, _, e = s.DocumentWindow(project, "")
	if e != nil || len(rows) != 1 || rows[0] != before {
		t.Fatal("derived rebuild lost tombstone", rows, e)
	}
	if e = os.WriteFile(filepath.Join(root, "new.md"), original, 0600); e != nil {
		t.Fatal(e)
	}
	call("upsert", "new.md", revision, false)
}
