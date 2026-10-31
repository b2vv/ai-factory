package documents

import (
	"errors"
	"os"
	"path/filepath"
	"testing"
)

func TestLedgerBudgetRefusalPrecedesTemporaryFile(t *testing.T) {
	root, e := filepath.EvalSymlinks(t.TempDir())
	if e != nil {
		t.Fatal(e)
	}
	source := []byte("<!-- factory-document-id: \"stable\" -->\nSynthetic\n")
	if e = os.WriteFile(filepath.Join(root, "source.md"), source, 0600); e != nil {
		t.Fatal(e)
	}
	called := false
	_, e = UpdateBudgeted(root, "ledger.md", "stable", "source.md", "", false, func(cost int64) error {
		called = true
		if cost <= 0 {
			t.Fatal("no replacement cost")
		}
		return errors.New("full")
	})
	if e == nil || !called {
		t.Fatal("budget refusal bypassed", e)
	}
	if _, e = os.Stat(filepath.Join(root, "ledger.md")); !os.IsNotExist(e) {
		t.Fatal("refused ledger published", e)
	}
	files, e := filepath.Glob(filepath.Join(root, ".document-ledger-*"))
	if e != nil || len(files) != 0 {
		t.Fatal("refusal left staging files", files, e)
	}
	got, e := os.ReadFile(filepath.Join(root, "source.md"))
	if e != nil || string(got) != string(source) {
		t.Fatal("source changed", e)
	}
}
