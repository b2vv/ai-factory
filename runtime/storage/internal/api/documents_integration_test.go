//go:build integration

package api_test

import (
	"aifactory.local/storage/internal/archive"
	"aifactory.local/storage/internal/documents"
	"aifactory.local/storage/internal/registry"
	"aifactory.local/storage/internal/search"
	"context"
	"fmt"
	"net/http"
	"os"
	"path/filepath"
	"testing"
	"time"
)

func TestDocumentHTTPProvenanceStaleTombstoneAndScopedGrant(t *testing.T) {
	dsn := os.Getenv("PG_DSN")
	if dsn == "" {
		t.Skip("PG_DSN unavailable")
	}
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	idx, e := search.Open(ctx, dsn)
	if e != nil {
		t.Fatal(e)
	}
	defer idx.Close()
	project := fmt.Sprintf("document_http_%d", time.Now().UnixNano())
	defer idx.Purge(project)
	ts, s, _, d := captureServer(t, archive.NewMemStore(), nil)
	s.SetSearchStore(idx)
	op := registry.Principal{ID: "op", Kind: registry.Operator}
	if e = d.MintProject(op, project, project); e != nil {
		t.Fatal(e)
	}
	root, e := filepath.EvalSymlinks(t.TempDir())
	if e != nil {
		t.Fatal(e)
	}
	if e = os.WriteFile(filepath.Join(root, "note.md"), []byte("<!-- factory-document-id: \"doc\" -->\n# Synthetic source\n"), 0600); e != nil {
		t.Fatal(e)
	}
	revision, e := documents.Update(root, "ledger.md", "doc", "note.md", "", false)
	if e != nil {
		t.Fatal(e)
	}
	if e = idx.ReplaceDocuments(project, root, "ledger.md", revision); e != nil {
		t.Fatal(e)
	}
	_, g := do(t, http.MethodPost, ts.URL+"/v1/grants", opHdr(), map[string]any{"principal_id": "doc-agent", "kind": "agent", "projects": []string{project}, "ops": []string{"search"}, "secret": "synthetic-doc"})
	epoch := itoa(int64(g["epoch"].(float64)))
	query := func(path string) (int, map[string]any) {
		return agentQuery(t, ts.URL, path, "doc-agent", epoch, "synthetic-doc")
	}
	path := "/v1/documents/query?project=" + project
	code, b := query(path)
	if code != 200 || len(b["sources"].([]any)) != 1 {
		t.Fatal(code, b)
	}
	ref := b["sources"].([]any)[0].(map[string]any)
	if ref["Path"] != "note.md" || ref["ID"] != "doc" || ref["Revision"] == "" || ref["Root"] != nil {
		t.Fatal("missing or escaping provenance", ref)
	}
	if code, _ = query("/v1/archive/query?project=" + project); code != 403 {
		t.Fatal("search grant expanded to archive", code)
	}
	if code, _ = query("/v1/documents/query?project=foreign"); code != 403 {
		t.Fatal("cross project", code)
	}
	if e = os.Remove(filepath.Join(root, "note.md")); e != nil {
		t.Fatal(e)
	}
	revision, e = documents.Update(root, "ledger.md", "doc", "note.md", revision, true)
	if e != nil {
		t.Fatal(e)
	}
	code, b = query(path)
	if code != 200 || len(b["sources"].([]any)) != 0 || b["derived_stale"] != true {
		t.Fatal("stale deleted document served", code, b)
	}
	if e = idx.ReplaceDocuments(project, root, "ledger.md", revision); e != nil {
		t.Fatal(e)
	}
	code, b = query(path)
	if code != 200 || len(b["sources"].([]any)) != 1 || b["sources"].([]any)[0].(map[string]any)["Deleted"] != true {
		t.Fatal("tombstone missing", code, b)
	}
	if _, e = d.DeleteProjectBarrier(op, project); e != nil {
		t.Fatal(e)
	}
	code, b = query(path)
	if code != 200 || len(b["sources"].([]any)) != 0 {
		t.Fatal("barred metadata served", code, b)
	}
	if e = d.RevokeGrant(op, "doc-agent"); e != nil {
		t.Fatal(e)
	}
	if code, _ = query(path); code != 403 {
		t.Fatal("revoked grant served", code)
	}
}
