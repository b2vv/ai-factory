//go:build integration

package api_test

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"fmt"
	"net/http"
	"os"
	"path/filepath"
	"sync"
	"testing"
	"time"

	"aifactory.local/storage/internal/archive"
	"aifactory.local/storage/internal/registry"
	"aifactory.local/storage/internal/workflow"
)

// The HTTP boundary uses actual PostgreSQL and a verified file cutover. The
// admission meter is synthetic here; physical capacity is a separate criterion.
func TestWorkflowHTTPRealPGCutoverCASAndRecovery(t *testing.T) {
	dsn := os.Getenv("PG_DSN")
	if dsn == "" {
		t.Skip("BLOCKED: PG_DSN unavailable")
	}
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	pg, e := workflow.OpenPostgres(ctx, dsn)
	if e != nil {
		t.Fatal(e)
	}
	defer pg.Close()
	ts, s, _, d := captureServer(t, archive.NewMemStore(), nil)
	s.SetWorkflowStore(pg)
	op := registry.Principal{ID: "op", Kind: registry.Operator}
	project := fmt.Sprintf("http_workflow_%d", time.Now().UnixNano())
	other := project + "_other"
	for _, p := range []string{project, other} {
		if e = d.MintProject(op, p, p); e != nil {
			t.Fatal(e)
		}
	}
	doc, e := workflow.Document([]workflow.Task{{ID: "task", Version: 1, Fields: map[string]string{"status": "ready"}}})
	if e != nil {
		t.Fatal(e)
	}
	path := filepath.Join(t.TempDir(), "workflow.md")
	if e = os.WriteFile(path, doc, 0600); e != nil {
		t.Fatal(e)
	}
	hash := sha256.Sum256(doc)
	receipt, e := workflow.Cutover(d, pg, op, project, path, hex.EncodeToString(hash[:]), registry.OwnerPostgres)
	if e != nil {
		t.Fatal(e)
	}
	emptyDoc, e := workflow.Document(nil)
	if e != nil {
		t.Fatal(e)
	}
	otherPath := filepath.Join(t.TempDir(), "other.md")
	if e = os.WriteFile(otherPath, emptyDoc, 0600); e != nil {
		t.Fatal(e)
	}
	otherHash := sha256.Sum256(emptyDoc)
	if code, response := do(t, http.MethodPost, ts.URL+"/v1/workflow/cutover", opHdr(), map[string]any{"project": other, "document": otherPath, "revision": hex.EncodeToString(otherHash[:]), "to": "postgres", "expected_epoch": 1, "edits_frozen": true}); code != 200 {
		t.Fatal("enable other", code, response)
	}
	_, g := do(t, "POST", ts.URL+"/v1/grants", opHdr(), map[string]any{"principal_id": "real-workflow-agent", "kind": "agent", "projects": []string{project, other}, "ops": []string{"workflow.read", "workflow.write"}, "secret": "synthetic"})
	headers := map[string]string{"X-Principal-Id": "real-workflow-agent", "X-Grant-Epoch": itoa(int64(g["epoch"].(float64))), "X-Secret": "synthetic"}
	endpoint := ts.URL + "/v1/workflow/task?project=" + project + "&id=task"
	const writers = 8
	statuses := make(chan int, writers)
	var wg sync.WaitGroup
	for i := 0; i < writers; i++ {
		wg.Add(1)
		go func(i int) {
			defer wg.Done()
			code, _ := do(t, http.MethodPut, endpoint, headers, map[string]any{"expected_version": 1, "epoch": receipt.NewEpoch, "fields": map[string]string{"winner": fmt.Sprint(i)}})
			statuses <- code
		}(i)
	}
	wg.Wait()
	close(statuses)
	wins, conflicts := 0, 0
	for code := range statuses {
		switch code {
		case 200:
			wins++
		case 409:
			conflicts++
		default:
			t.Fatalf("unexpected status %d", code)
		}
	}
	if wins != 1 || conflicts != writers-1 {
		t.Fatalf("CAS wins=%d conflicts=%d", wins, conflicts)
	}
	stored, ok, e := pg.Get(project, "task")
	if e != nil || !ok || stored.Version != 2 {
		t.Fatalf("durable CAS: %+v %v %v", stored, ok, e)
	}
	if code, _ := do(t, http.MethodPut, endpoint, headers, map[string]any{"expected_version": 2, "epoch": 1, "fields": map[string]string{"bad": "stale"}}); code != 409 {
		t.Fatal("epoch", code)
	}
	if code, _ := do(t, http.MethodGet, endpoint, headers, nil); code != 200 {
		t.Fatal("read", code)
	}
	cutover := map[string]any{"project": project, "document": path, "revision": hex.EncodeToString(hash[:]), "to": "markdown", "expected_epoch": receipt.NewEpoch, "edits_frozen": true}
	if code, _ := do(t, http.MethodPost, ts.URL+"/v1/workflow/cutover", headers, cutover); code != 401 {
		t.Fatal("agent cutover", code)
	}
	if code, response := do(t, http.MethodPost, ts.URL+"/v1/workflow/cutover", opHdr(), cutover); code != 200 {
		t.Fatal("operator cutover", code, response)
	}
	if code, _ := do(t, http.MethodPost, ts.URL+"/v1/workflow/cutover", opHdr(), cutover); code != 409 {
		t.Fatal("stale cutover repeated", code)
	}
	if code, _ := do(t, http.MethodGet, endpoint, headers, nil); code != 403 {
		t.Fatal("revoked after cutover", code)
	}
	// The other project remains authorized, including a genuine backend absence.
	if code, _ := do(t, http.MethodGet, ts.URL+"/v1/workflow/task?project="+other+"&id=task", headers, nil); code != 404 {
		t.Fatal("other project affected", code)
	}
	if code, response := do(t, http.MethodPut, ts.URL+"/v1/workflow/task?project="+other+"&id=task", headers, map[string]any{"expected_version": 0, "epoch": 2, "fields": map[string]string{"status": "still-writable"}}); code != 200 {
		t.Fatal("other project write interrupted", code, response)
	}
	exported, e := os.ReadFile(path)
	if e != nil {
		t.Fatal(e)
	}
	newHash := sha256.Sum256(exported)
	tasks, e := workflow.VerifiedDocument(path, hex.EncodeToString(newHash[:]))
	if e != nil || len(tasks) != 1 || tasks[0].Version != 2 {
		t.Fatalf("verified export: %+v %v", tasks, e)
	}
	pg.Close()
	if code, _ := do(t, http.MethodGet, ts.URL+"/v1/workflow/task?project="+other+"&id=task", headers, nil); code != 503 {
		t.Fatal("backend error hidden", code)
	}
	if code, _ := do(t, http.MethodPost, ts.URL+"/v1/workflow/cutover", opHdr(), map[string]any{"project": other, "document": otherPath, "revision": hex.EncodeToString(otherHash[:]), "to": "markdown", "expected_epoch": 2, "edits_frozen": true}); code != 503 {
		t.Fatal("backend outage must BLOCK cutover", code)
	}
	owner, epoch, _ := d.Registry().WorkflowAuthority(other)
	if owner != registry.OwnerPostgres || epoch != 2 {
		t.Fatal("outage transferred authority", owner, epoch)
	}

}
