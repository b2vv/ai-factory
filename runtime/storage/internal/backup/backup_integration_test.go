//go:build integration

package backup

import (
	"aifactory.local/storage/internal/archive"
	"aifactory.local/storage/internal/authz"
	"aifactory.local/storage/internal/control"
	"aifactory.local/storage/internal/registry"
	"aifactory.local/storage/internal/search"
	"aifactory.local/storage/internal/workflow"
	"bytes"
	"context"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

func TestRealDatabasesRestoreLatestAuthorityAndIntegrity(t *testing.T) {
	dsn, uri := os.Getenv("PG_DSN"), os.Getenv("MONGO_URI")
	if dsn == "" || uri == "" {
		t.Skip("BLOCKED: real PG and Mongo required")
	}
	ctx, cancel := context.WithTimeout(context.Background(), 15*time.Second)
	defer cancel()
	pg, e := workflow.OpenPostgres(ctx, dsn)
	if e != nil {
		t.Fatal(e)
	}
	defer pg.Close()
	mongo, e := archive.OpenMongo(ctx, uri, "factory_test", "backup_synthetic")
	if e != nil {
		t.Fatal(e)
	}
	defer mongo.Close()
	dir := filepath.Join(t.TempDir(), "control")
	d, e := control.Initialize(dir)
	if e != nil {
		t.Fatal(e)
	}
	defer func() { d.Close() }()
	op := registry.Principal{ID: "op", Kind: registry.Operator}
	project := fmt.Sprintf("backup-%d", time.Now().UnixNano())
	if e = d.MintProject(op, project, "synthetic"); e != nil {
		t.Fatal(e)
	}
	if _, e = d.SetConsent(op, project, "synthetic", "capture", true); e != nil {
		t.Fatal(e)
	}
	grant := registry.Grant{PrincipalID: "agent", Kind: registry.Agent, Projects: map[string]bool{project: true}, Ops: map[registry.Op]bool{registry.OpArchiveQuery: true}, Secret: "synthetic"}
	if e = d.IssueGrant(op, grant); e != nil {
		t.Fatal(e)
	}
	idx, e := search.Open(ctx, dsn)
	if e != nil {
		t.Fatal(e)
	}
	defer idx.Close()
	for _, session := range []string{"allowed", "deleted"} {
		r := archive.Record{Project: project, Provider: "synthetic", SourceInstance: "fixture", SessionID: session, MessageID: "one", Seq: 1, Role: "user", Text: "synthetic original", ConsentEpoch: 1}
		if e = mongo.Put(r); e != nil {
			t.Fatal(e)
		}
		if e = idx.Put(r); e != nil {
			t.Fatal(e)
		}
	}
	if e = pg.CAS(project, workflow.Task{ID: "task", Version: 1, Fields: map[string]string{"status": "pending"}}, 0); e != nil {
		t.Fatal(e)
	}
	var data bytes.Buffer
	if e = Create(d, op, mongo, pg, []string{project}, &data); e != nil {
		t.Fatal(e)
	}
	if _, e = d.DeleteSessionBarrier(op, project, "deleted"); e != nil {
		t.Fatal(e)
	}
	if e = d.RevokeGrant(op, "agent"); e != nil {
		t.Fatal(e)
	}
	d.Close()
	d, e = control.Open(dir)
	if e != nil {
		t.Fatal(e)
	}
	// Only this unique synthetic project's rows are removed to simulate empty restore targets.
	if _, e = mongo.Purge(project, ""); e != nil {
		t.Fatal(e)
	}
	if e = pg.Replace(project, nil); e != nil {
		t.Fatal(e)
	}
	corrupt := append([]byte{}, data.Bytes()...)
	for i := range corrupt {
		if corrupt[i] == 'p' {
			corrupt[i] = 'x'
			break
		}
	}
	if _, e = Restore(d, op, mongo, pg, bytes.NewReader(corrupt), time.Now()); e == nil {
		t.Fatal("corrupt backup restored")
	}
	if refs, _, e := idx.Window(project, "", ""); e != nil || len(refs) != 2 {
		t.Fatal("corrupt preflight changed derived rows", refs, e)
	}
	result, e := Restore(d, op, mongo, pg, bytes.NewReader(data.Bytes()), time.Now())
	if e != nil {
		t.Fatal(e)
	}
	if refs, _, e := idx.Window(project, "", ""); e != nil || len(refs) != 0 {
		t.Fatal("stale index survived restore", refs, e)
	}
	if result.Restored != 1 || result.Withheld != 1 || result.Projects != 1 {
		t.Fatal(result)
	}
	records, e := mongo.Fetch(project)
	if e != nil || len(records) != 1 || records[0].SessionID != "allowed" {
		t.Fatal(records, e)
	}
	task, found, e := pg.Get(project, "task")
	if e != nil || !found || task.Version != 1 || task.Fields["status"] != "pending" {
		t.Fatal(task, found, e)
	}
	if e = authz.Authorize(d.Registry(), authz.Token{PrincipalID: "agent", Kind: registry.Agent, Epoch: 1, Secret: "synthetic"}, project, registry.OpArchiveQuery); e == nil {
		t.Fatal("backup resurrected revoked grant")
	}
	if _, e = Restore(d, op, mongo, pg, bytes.NewReader(data.Bytes()), time.Now()); e == nil {
		t.Fatal("nonempty destination overwritten")
	}
	// Revoke/regrant must permanently withhold both old-epoch records after restart.
	if _, e = d.SetConsent(op, project, "synthetic", "capture", false); e != nil {
		t.Fatal(e)
	}
	if _, e = d.SetConsent(op, project, "synthetic", "capture", true); e != nil {
		t.Fatal(e)
	}
	d.Close()
	d, e = control.Open(dir)
	if e != nil {
		t.Fatal(e)
	}
	if _, e = mongo.Purge(project, ""); e != nil {
		t.Fatal(e)
	}
	if e = pg.Replace(project, nil); e != nil {
		t.Fatal(e)
	}
	result, e = Restore(d, op, mongo, pg, bytes.NewReader(data.Bytes()), time.Now())
	if e != nil || result.Restored != 0 || result.Withheld != 2 {
		t.Fatal(result, e)
	}
}

func TestBackupOperatorExecutable(t *testing.T) {
	t.Skip("DEFERRED: owner excluded backups; backup-dependent operator activation is disabled")
	dsn, uri := os.Getenv("PG_DSN"), os.Getenv("MONGO_URI")
	if dsn == "" || uri == "" {
		t.Skip("BLOCKED: real PG and Mongo required")
	}
	ctx, cancel := context.WithTimeout(context.Background(), 15*time.Second)
	defer cancel()
	pg, e := workflow.OpenPostgres(ctx, dsn)
	if e != nil {
		t.Fatal(e)
	}
	defer pg.Close()
	mongo, e := archive.OpenMongo(ctx, uri, "factory_test", "backup_operator_synthetic")
	if e != nil {
		t.Fatal(e)
	}
	defer mongo.Close()
	dir := t.TempDir()
	state := filepath.Join(dir, "control")
	d, e := control.Initialize(state)
	if e != nil {
		t.Fatal(e)
	}
	op := registry.Principal{ID: "op", Kind: registry.Operator}
	project := fmt.Sprintf("backup-cli-%d", time.Now().UnixNano())
	if e = d.MintProject(op, project, "synthetic"); e != nil {
		t.Fatal(e)
	}
	if _, e = d.SetConsent(op, project, "synthetic", "capture", true); e != nil {
		t.Fatal(e)
	}
	d.Close()
	r := archive.Record{Project: project, Provider: "synthetic", SourceInstance: "fixture", SessionID: "s", MessageID: "m", Seq: 1, Text: strings.Repeat("synthetic ", 1<<17), ConsentEpoch: 1}
	if e = mongo.Put(r); e != nil {
		t.Fatal(e)
	}
	if e = pg.CAS(project, workflow.Task{ID: "task", Version: 1, Fields: map[string]string{"status": "pending"}}, 0); e != nil {
		t.Fatal(e)
	}
	for n := 2; n <= 30; n++ {
		row := r
		row.MessageID = fmt.Sprint(n)
		row.Seq = n
		if e = mongo.Put(row); e != nil {
			t.Fatal(e)
		}
	}
	backups := filepath.Join(dir, "backups")
	if e = os.Mkdir(backups, 0700); e != nil {
		t.Fatal(e)
	}
	for name, value := range map[string]string{"mongo": uri, "pg": dsn} {
		if e = os.WriteFile(filepath.Join(dir, name), []byte(value), 0600); e != nil {
			t.Fatal(e)
		}
	}
	binary := filepath.Join(dir, "backup-operator")
	if out, e := exec.Command("go", "build", "-o", binary, "../../cmd/backup-operator").CombinedOutput(); e != nil {
		t.Fatalf("build: %v %s", e, out)
	}
	args := []string{"-state", state, "-directory", backups, "-name", "test.backup", "-mongo-uri-file", filepath.Join(dir, "mongo"), "-pg-dsn-file", filepath.Join(dir, "pg"), "-mongo-db", "factory_test", "-mongo-collection", "backup_operator_synthetic", "-projects", project, "-exclusive-window", "-free-headroom", "0"}
	if out, e := exec.Command(binary, append(args, "-mode", "create")...).CombinedOutput(); e != nil {
		t.Fatalf("create: %v %s", e, out)
	}
	if st, e := os.Stat(filepath.Join(backups, "test.backup")); e != nil || st.Size() <= MaxBytes {
		t.Fatal("executable backup did not exceed legacy bound", e)
	}
	if _, e = mongo.Purge(project, ""); e != nil {
		t.Fatal(e)
	}
	if e = pg.Replace(project, nil); e != nil {
		t.Fatal(e)
	}
	if out, e := exec.Command(binary, append(args, "-mode", "restore")...).CombinedOutput(); e != nil {
		t.Fatalf("restore: %v %s", e, out)
	}
	got, found, e := mongo.Lookup(r)
	if e != nil || !found || got != r {
		t.Fatal(got, found, e)
	}
	for n := 2; n <= 30; n++ {
		row := r
		row.MessageID = fmt.Sprint(n)
		row.Seq = n
		got, found, e := mongo.Lookup(row)
		if e != nil || !found || got != row {
			t.Fatal("large restore row mismatch", n, found, e)
		}
	}
	if e = exec.Command(binary, append(args, "-mode", "restore")...).Run(); e == nil {
		t.Fatal("restore overwrote nonempty target")
	}
	if e = exec.Command(binary, append(args, "-mode", "create")...).Run(); e == nil {
		t.Fatal("backup overwritten")
	}
	writeExpiryFixture(t, backups, "expired.backup", time.Now().Add(-31*24*time.Hour))
	expiryArgs := []string{"-mode", "expire", "-state", state, "-directory", backups, "-exclusive-window", "-free-headroom", "0"}
	if out, e := exec.Command(binary, expiryArgs...).CombinedOutput(); e != nil {
		t.Fatalf("expiry executable: %v %s", e, out)
	}
	if _, e := os.Stat(filepath.Join(backups, "expired.backup")); !os.IsNotExist(e) {
		t.Fatal("expired backup remains", e)
	}
	if _, e := os.Stat(filepath.Join(backups, "test.backup")); e != nil {
		t.Fatal("current stream deleted", e)
	}

}
