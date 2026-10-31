package documents

import (
	"encoding/json"
	"os"
	"path/filepath"
	"testing"
)

func TestStableDocumentRenameDeletionAndNoResurrection(t *testing.T) {
	root, e := filepath.EvalSymlinks(t.TempDir())
	if e != nil {
		t.Fatal(e)
	}
	id := "stable-doc"
	encoded, _ := json.Marshal(id)
	raw := []byte("<!-- factory-document-id: " + string(encoded) + " -->\n# Human prose\nNever rewritten.\n")
	old := filepath.Join(root, "old.md")
	if e = os.WriteFile(old, raw, 0600); e != nil {
		t.Fatal(e)
	}
	rev, e := Update(root, "ledger.md", id, "old.md", "", false)
	if e != nil {
		t.Fatal(e)
	}
	newPath := filepath.Join(root, "renamed.md")
	if e = os.Rename(old, newPath); e != nil {
		t.Fatal(e)
	}
	rev, e = Update(root, "ledger.md", id, "renamed.md", rev, false)
	if e != nil {
		t.Fatal(e)
	}
	rows, _, e := Read(filepath.Join(root, "ledger.md"))
	if e != nil || len(rows) != 1 || rows[0].ID != id || rows[0].Version != 2 || rows[0].Revision != Digest(raw) {
		t.Fatal(rows, e)
	}
	if got, e := os.ReadFile(newPath); e != nil || string(got) != string(raw) {
		t.Fatal("human bytes changed", e)
	}
	if _, e = Update(root, "ledger.md", id, "renamed.md", rev, true); e == nil {
		t.Fatal("tombstoned present file")
	}
	if e = os.Remove(newPath); e != nil {
		t.Fatal(e)
	}
	rev, e = Update(root, "ledger.md", id, "renamed.md", rev, true)
	if e != nil {
		t.Fatal(e)
	}
	rows, _, e = Read(filepath.Join(root, "ledger.md"))
	if e != nil || !rows[0].Deleted || rows[0].Version != 3 {
		t.Fatal(rows, e)
	}
	if e = os.WriteFile(newPath, raw, 0600); e != nil {
		t.Fatal(e)
	}
	if _, e = Update(root, "ledger.md", id, "renamed.md", rev, false); e == nil {
		t.Fatal("deleted ID resurrected")
	}
}
func TestLedgerConflictsManualEditsAndEscapesFailClosed(t *testing.T) {
	root, e := filepath.EvalSymlinks(t.TempDir())
	if e != nil {
		t.Fatal(e)
	}
	b := []byte("<!-- factory-document-id: \"doc\" -->\ntext\n")
	if e = os.WriteFile(filepath.Join(root, "doc.md"), b, 0600); e != nil {
		t.Fatal(e)
	}
	rev, e := Update(root, "ledger.md", "doc", "doc.md", "", false)
	if e != nil {
		t.Fatal(e)
	}
	if _, e = Update(root, "ledger.md", "doc", "doc.md", "stale", false); e == nil {
		t.Fatal("stale revision accepted")
	}
	if _, e = Update(root, "ledger.md", "doc", "../escape", rev, false); e == nil {
		t.Fatal("escape accepted")
	}
	if e = os.Symlink(filepath.Join(root, "doc.md"), filepath.Join(root, "link.md")); e != nil {
		t.Fatal(e)
	}
	if _, e = Update(root, "ledger.md", "doc", "link.md", rev, false); e == nil {
		t.Fatal("symlink accepted")
	}
	ledger := filepath.Join(root, "ledger.md")
	raw, e := os.ReadFile(ledger)
	if e != nil {
		t.Fatal(e)
	}
	raw[len(raw)/2] ^= 1
	if e = os.WriteFile(ledger, raw, 0600); e != nil {
		t.Fatal(e)
	}
	if _, _, e = Read(ledger); e == nil {
		t.Fatal("manual edit accepted")
	}
}
