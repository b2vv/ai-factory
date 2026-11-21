//go:build integration

package search

import (
	"aifactory.local/storage/internal/documents"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"testing"
	"time"
)

func TestDocumentIndexBudgetRefusalPrecedesDeleteAndInsert(t *testing.T) {
	s := realStore(t)
	project := fmt.Sprintf("budget_docs_%d", time.Now().UnixNano())
	defer s.Purge(project)
	root := t.TempDir()
	for _, id := range []string{"a", "b"} {
		if e := os.WriteFile(filepath.Join(root, id+".md"), []byte("<!-- factory-document-id: \""+id+"\" -->\nSynthetic\n"), 0600); e != nil {
			t.Fatal(e)
		}
	}
	rev, e := documents.Update(root, "ledger.md", "a", "a.md", "", false)
	if e != nil {
		t.Fatal(e)
	}
	if e = s.ReplaceDocuments(project, root, "ledger.md", rev); e != nil {
		t.Fatal(e)
	}
	rev, e = documents.Update(root, "ledger.md", "b", "b.md", rev, false)
	if e != nil {
		t.Fatal(e)
	}
	called := false
	e = s.ReplaceDocumentsBudgeted(project, root, "ledger.md", rev, func(cost int64) error {
		called = true
		if cost <= 0 {
			t.Fatal("missing index cost")
		}
		return errors.New("full")
	})
	if e == nil || !called {
		t.Fatal("budget refusal bypassed", e)
	}
	refs, _, e := s.DocumentWindow(project, "")
	if e != nil || len(refs) != 1 || refs[0].ID != "a" {
		t.Fatal("index changed before admission", refs, e)
	}
}
