package api_test

import (
	"aifactory.local/storage/internal/archive"
	"aifactory.local/storage/internal/registry"
	"aifactory.local/storage/internal/workflow"
	"errors"
	"net/http"
	"strings"
	"testing"
)

func TestWorkflowHTTPVersionsEpochAndProjectIsolation(t *testing.T) {
	ts, s, _, d := captureServer(t, archive.NewMemStore(), nil)
	s.SetWorkflowStore(workflow.NewMemStore())
	op := registry.Principal{ID: "op", Kind: registry.Operator}
	for _, p := range []string{"p", "q"} {
		if e := d.MintProject(op, p, p); e != nil {
			t.Fatal(e)
		}
	}
	if _, e := d.CutoverWorkflow(op, "p", registry.OwnerMarkdown, 1, registry.OwnerPostgres, func() (string, string, error) { return "synthetic", strings.Repeat("a", 64), nil }); e != nil {
		t.Fatal(e)
	}
	_, g := do(t, "POST", ts.URL+"/v1/grants", opHdr(), map[string]any{"principal_id": "workflow-agent", "kind": "agent", "projects": []string{"p"}, "ops": []string{"workflow.read", "workflow.write"}, "secret": "synthetic"})
	headers := map[string]string{"X-Principal-Id": "workflow-agent", "X-Grant-Epoch": itoa(int64(g["epoch"].(float64))), "X-Secret": "synthetic"}
	endpoint := ts.URL + "/v1/workflow/task?project=p&id=t"
	for _, tc := range []struct {
		version, epoch int
		status         int
	}{{0, 2, 200}, {0, 2, 409}, {1, 1, 409}, {1, 2, 200}} {
		code, response := do(t, http.MethodPut, endpoint, headers, map[string]any{"expected_version": tc.version, "epoch": tc.epoch, "fields": map[string]string{"status": "ready"}})
		if code != tc.status {
			t.Fatal(tc, code, response)
		}
	}
	if code, _ := do(t, http.MethodGet, endpoint, headers, nil); code != 200 {
		t.Fatal(code)
	}
	if code, _ := do(t, http.MethodGet, ts.URL+"/v1/workflow/task?project=q&id=t", headers, nil); code != 403 {
		t.Fatal("foreign project", code)
	}
	if _, e := d.CutoverWorkflow(op, "p", registry.OwnerPostgres, 2, registry.OwnerMarkdown, func() (string, string, error) { return "synthetic", strings.Repeat("b", 64), nil }); e != nil {
		t.Fatal(e)
	}
	if code, _ := do(t, http.MethodGet, endpoint, headers, nil); code != 403 {
		t.Fatal("revoked project", code)
	}
}

type blockedWorkflowRead struct {
	*workflow.MemStore
	entered, release chan struct{}
}

func (s *blockedWorkflowRead) Get(project, id string) (workflow.Task, bool, error) {
	close(s.entered)
	<-s.release
	return workflow.Task{}, false, errors.New("synthetic backend diagnostic")
}
func TestWorkflowReadReauthorizesEvenWhenBackendFails(t *testing.T) {
	ts, s, _, d := captureServer(t, archive.NewMemStore(), nil)
	store := &blockedWorkflowRead{workflow.NewMemStore(), make(chan struct{}), make(chan struct{})}
	s.SetWorkflowStore(store)
	if e := d.MintProject(registry.Principal{ID: "op", Kind: registry.Operator}, "p", "p"); e != nil {
		t.Fatal(e)
	}
	_, g := do(t, "POST", ts.URL+"/v1/grants", opHdr(), map[string]any{"principal_id": "w", "kind": "agent", "projects": []string{"p"}, "ops": []string{"workflow.read"}, "secret": "synthetic"})
	done := make(chan int, 1)
	go func() {
		code, _ := agentQuery(t, ts.URL, "/v1/workflow/task?project=p&id=t", "w", itoa(int64(g["epoch"].(float64))), "synthetic")
		done <- code
	}()
	<-store.entered
	if code, _ := do(t, "POST", ts.URL+"/v1/grants/revoke", opHdr(), map[string]string{"principal_id": "w"}); code != 200 {
		t.Fatal(code)
	}
	close(store.release)
	if code := <-done; code != 403 {
		t.Fatal("post-revoke diagnostic disclosed", code)
	}
}
