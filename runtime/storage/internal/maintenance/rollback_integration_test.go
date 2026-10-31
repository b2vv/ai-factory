//go:build integration

package maintenance

import (
	"aifactory.local/storage/internal/archive"
	"aifactory.local/storage/internal/authz"
	"aifactory.local/storage/internal/backup"
	"aifactory.local/storage/internal/control"
	"aifactory.local/storage/internal/documents"
	"aifactory.local/storage/internal/registry"
	"aifactory.local/storage/internal/search"
	"aifactory.local/storage/internal/workflow"
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"github.com/jackc/pgx/v5"
	"net/url"
	"os"
	"os/exec"
	"path/filepath"
	"testing"
	"time"
)

func isolatedDSN(t *testing.T) string {
	t.Helper()
	dsn := os.Getenv("PG_DSN")
	if dsn == "" {
		t.Skip("BLOCKED: synthetic PostgreSQL required")
	}
	ctx := context.Background()
	admin, e := pgx.Connect(ctx, dsn)
	if e != nil {
		t.Fatal(e)
	}
	schema := fmt.Sprintf("b5_synthetic_%d", time.Now().UnixNano())
	quoted := pgx.Identifier{schema}.Sanitize()
	if _, e = admin.Exec(ctx, "CREATE SCHEMA "+quoted); e != nil {
		admin.Close(ctx)
		t.Fatal(e)
	}
	t.Cleanup(func() {
		_, e := admin.Exec(context.Background(), "DROP SCHEMA "+quoted+" CASCADE")
		admin.Close(context.Background())
		if e != nil {
			t.Error(e)
		}
	})
	u, e := url.Parse(dsn)
	if e != nil {
		t.Fatal(e)
	}
	q := u.Query()
	q.Set("search_path", schema)
	u.RawQuery = q.Encode()
	return u.String()
}
func TestB5ExecutableRefusesUnsafeThenVerifiedRoundTrip(t *testing.T) {
	t.Skip("DEFERRED: owner excluded backups; backup-dependent operator activation is disabled")
	dsn := isolatedDSN(t)
	ctx := context.Background()
	pg, e := workflow.OpenPostgres(ctx, dsn)
	if e != nil {
		t.Fatal(e)
	}
	defer func() { pg.Close() }()
	dir := t.TempDir()
	state := filepath.Join(dir, "control")
	d, e := control.Initialize(state)
	if e != nil {
		t.Fatal(e)
	}
	defer func() { d.Close() }()
	op := registry.Principal{ID: "op", Kind: registry.Operator}
	for _, p := range []string{"a", "b"} {
		if e = d.MintProject(op, p, p); e != nil {
			t.Fatal(e)
		}
	}
	if e = d.IssueGrant(op, registry.Grant{PrincipalID: "agent", Kind: registry.Agent, Projects: map[string]bool{"a": true, "b": true}, Ops: map[registry.Op]bool{registry.OpWorkflowWrite: true}, Secret: "synthetic"}); e != nil {
		t.Fatal(e)
	}
	doc := filepath.Join(dir, "a.md")
	raw, e := workflow.Document([]workflow.Task{{ID: "task", Version: 1, Fields: map[string]string{"status": "pending"}}})
	if e != nil {
		t.Fatal(e)
	}
	if e = os.WriteFile(doc, raw, 0600); e != nil {
		t.Fatal(e)
	}
	receipt, e := workflow.Cutover(d, pg, op, "a", doc, Revision(raw), registry.OwnerPostgres)
	if e != nil {
		t.Fatal(e)
	}
	if e = workflow.New(d.Registry(), pg).Write("a", "task", 1, receipt.NewEpoch, map[string]string{"status": "done"}); e != nil {
		t.Fatal(e)
	}
	mem := archive.NewMemStore()
	var stale bytes.Buffer
	if e = backup.Create(d, op, mem, pg, []string{"a"}, &stale); e != nil {
		t.Fatal(e)
	}
	sources := map[string]Source{"a": {Path: doc, Revision: Revision(raw)}}
	// Even a readable complete export is not an authority transfer.
	tasks, e := pg.Snapshot("a")
	if e != nil {
		t.Fatal(e)
	}
	raw, e = workflow.Document(tasks)
	if e != nil {
		t.Fatal(e)
	}
	if e = os.WriteFile(doc, raw, 0600); e != nil {
		t.Fatal(e)
	}
	sources["a"] = Source{Path: doc, Revision: Revision(raw)}
	if e = RollbackWorkflowV1(ctx, d, pg, op, bytes.NewReader(stale.Bytes()), sources, true); e == nil {
		t.Fatal("PG-owned data dropped after export-only")
	}
	if _, e = workflow.Cutover(d, pg, op, "a", doc, Revision(raw), registry.OwnerMarkdown); e != nil {
		t.Fatal(e)
	}
	d.Close()
	d, e = control.Open(state)
	if e != nil {
		t.Fatal(e)
	}
	tok := authz.Token{PrincipalID: "agent", Kind: registry.Agent, Epoch: 1, Secret: "synthetic"}
	if e = authz.Authorize(d.Registry(), tok, "a", registry.OpWorkflowWrite); e == nil {
		t.Fatal("A grant not revoked")
	}
	if e = authz.Authorize(d.Registry(), tok, "b", registry.OpWorkflowWrite); e != nil {
		t.Fatal("B disrupted", e)
	}
	raw, e = os.ReadFile(doc)
	if e != nil {
		t.Fatal(e)
	}
	sources["a"] = Source{Path: doc, Revision: Revision(raw)}
	idx, e := search.Open(ctx, dsn)
	if e != nil {
		t.Fatal(e)
	}
	defer idx.Close()
	if _, e = d.SetConsent(op, "a", "synthetic", "capture", true); e != nil {
		t.Fatal(e)
	}
	archived := archive.Record{Project: "a", Provider: "synthetic", SourceInstance: "i", SessionID: "s", MessageID: "m", Text: "backed source", ConsentEpoch: 1}
	if e = mem.Put(archived); e != nil {
		t.Fatal(e)
	}
	if e = idx.Put(archived); e != nil {
		t.Fatal(e)
	}
	body := []byte("<!-- factory-document-id: \"doc\" -->\n# Synthetic document\n")
	if e = os.WriteFile(filepath.Join(dir, "source.md"), body, 0600); e != nil {
		t.Fatal(e)
	}
	ledgerRevision, e := documents.Update(dir, "ledger.md", "doc", "source.md", "", false)
	if e != nil {
		t.Fatal(e)
	}
	if e = idx.ReplaceDocuments("a", dir, "ledger.md", ledgerRevision); e != nil {
		t.Fatal(e)
	}
	var good bytes.Buffer
	if e = backup.CreateStream(d, op, mem, pg, []string{"a"}, &good); e != nil {
		t.Fatal(e)
	}
	corruptedIndex := archived
	corruptedIndex.Text = "not in backup"
	if e = idx.Put(corruptedIndex); e != nil {
		t.Fatal(e)
	}
	if e = RollbackWorkflowV1(ctx, d, pg, op, bytes.NewReader(good.Bytes()), sources, true); e == nil {
		t.Fatal("index source mismatch dropped")
	}
	if e = idx.Put(archived); e != nil {
		t.Fatal(e)
	}
	for label, attempt := range map[string]func() error{
		"stale backup":            func() error { return RollbackWorkflowV1(ctx, d, pg, op, bytes.NewReader(stale.Bytes()), sources, true) },
		"missing acknowledgement": func() error { return RollbackWorkflowV1(ctx, d, pg, op, bytes.NewReader(good.Bytes()), sources, false) },
		"corrupt backup":          func() error { return RollbackWorkflowV1(ctx, d, pg, op, bytes.NewReader([]byte(`{}`)), sources, true) },
		"missing source":          func() error { return RollbackWorkflowV1(ctx, d, pg, op, bytes.NewReader(good.Bytes()), nil, true) },
	} {
		if e = attempt(); e == nil {
			t.Fatal("unsafe rollback accepted", label)
		}
		if _, found, e := pg.Get("a", "task"); e != nil || !found {
			t.Fatal("failed gate changed table", label, e)
		}
	}
	conn, e := pgx.Connect(ctx, dsn)
	if e != nil {
		t.Fatal(e)
	}
	defer conn.Close(ctx)
	if _, e = conn.Exec(ctx, `ALTER TABLE workflow_tasks ADD COLUMN unreviewed text`); e != nil {
		t.Fatal(e)
	}
	if e = RollbackWorkflowV1(ctx, d, pg, op, bytes.NewReader(good.Bytes()), sources, true); e == nil {
		t.Fatal("unreviewed table shape dropped")
	}
	if _, e = conn.Exec(ctx, `ALTER TABLE workflow_tasks DROP COLUMN unreviewed`); e != nil {
		t.Fatal(e)
	}
	binary := filepath.Join(dir, "migration-operator")
	if out, e := exec.Command("go", "build", "-o", binary, "../../cmd/migration-operator").CombinedOutput(); e != nil {
		t.Fatalf("build %v %s", e, out)
	}
	sourceJSON, e := json.Marshal(sources)
	if e != nil {
		t.Fatal(e)
	}
	for name, data := range map[string][]byte{"dsn": []byte(dsn), "sources": sourceJSON, "backup": good.Bytes()} {
		if e = os.WriteFile(filepath.Join(dir, name), data, 0600); e != nil {
			t.Fatal(e)
		}
	}
	d.Close()
	args := []string{"-state", state, "-pg-dsn-file", filepath.Join(dir, "dsn"), "-backup-file", filepath.Join(dir, "backup"), "-sources-file", filepath.Join(dir, "sources"), "-to", "0", "-exclusive-window"}
	if e = exec.Command(binary, args...).Run(); e == nil {
		t.Fatal("executable bypassed acknowledgement")
	}
	if out, e := exec.Command(binary, append(args, "-ack-derived-data-removal")...).CombinedOutput(); e != nil {
		t.Fatalf("verified rollback: %v %s", e, out)
	}
	var count int
	if e = conn.QueryRow(ctx, `SELECT count(*) FROM schema_migrations`).Scan(&count); e != nil || count != 0 {
		t.Fatal(count, e)
	}
	var relation *string
	if e = conn.QueryRow(ctx, `SELECT to_regclass('workflow_tasks')::text`).Scan(&relation); e != nil || relation != nil {
		t.Fatal(relation, e)
	}
	// Repeating the command must refuse, never auto-migrate schema up before down.
	if e = exec.Command(binary, append(args, "-ack-derived-data-removal")...).Run(); e == nil {
		t.Fatal("repeated down implicitly migrated")
	}
	pg.Close()
	pg, e = workflow.OpenPostgres(ctx, dsn)
	if e != nil {
		t.Fatal(e)
	}
	d, e = control.Open(state)
	if e != nil {
		t.Fatal(e)
	}
	if _, e = mem.Purge("a", ""); e != nil {
		t.Fatal(e)
	}
	result, e := backup.RestoreFile(d, op, mem, pg, bytes.NewReader(good.Bytes()), time.Now())
	if e != nil || result.Projects != 1 {
		t.Fatal(result, e)
	}
	rebuilt, e := search.Open(ctx, dsn)
	if e != nil {
		t.Fatal(e)
	}
	defer rebuilt.Close()
	restored, found, e := mem.Lookup(archived)
	if e != nil || !found {
		t.Fatal(found, e)
	}
	if e = rebuilt.Put(restored); e != nil {
		t.Fatal(e)
	}
	if e = rebuilt.ReplaceDocuments("a", dir, "ledger.md", ledgerRevision); e != nil {
		t.Fatal(e)
	}
	if ok, e := rebuilt.Matches(archived); e != nil || !ok {
		t.Fatal("index rebuild after rollback", ok, e)
	}
	task, found, e := pg.Get("a", "task")
	if e != nil || !found || task.Version != 2 || task.Fields["status"] != "done" {
		t.Fatal(task, found, e)
	}
	owner, epoch, _ := d.Registry().WorkflowAuthority("a")
	if owner != registry.OwnerMarkdown || epoch != 3 {
		t.Fatal(owner, epoch)
	}
	if e = authz.Authorize(d.Registry(), tok, "a", registry.OpWorkflowWrite); e == nil {
		t.Fatal("restore resurrected workflow grant")
	}
}
