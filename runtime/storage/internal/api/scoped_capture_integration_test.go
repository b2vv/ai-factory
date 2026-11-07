//go:build integration

package api_test

import (
	"aifactory.local/storage/internal/archive"
	"aifactory.local/storage/internal/budget"
	"aifactory.local/storage/internal/control"
	"aifactory.local/storage/internal/registry"
	"aifactory.local/storage/internal/search"
	"aifactory.local/storage/internal/workflow"
	"context"
	"fmt"
	"github.com/jackc/pgx/v5"
	"net/url"
	"os"
	"path/filepath"
	"testing"
	"time"
)

func TestScopedCaptureRealDatabases(t *testing.T) {
	uri, dsn := os.Getenv("MONGO_URI"), os.Getenv("PG_DSN")
	if uri == "" || dsn == "" {
		t.Skip("isolated Mongo/PG required; not native-agent evidence")
	}
	for _, route := range []string{"generic", "claude", "codex", "codex-v2"} {
		t.Run(route, func(t *testing.T) {
			ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
			defer cancel()
			schema := fmt.Sprintf("scoped_capture_%d", time.Now().UnixNano())
			admin, e := pgx.Connect(ctx, dsn)
			if e != nil {
				t.Fatal(e)
			}
			if _, e = admin.Exec(ctx, "CREATE SCHEMA "+pgx.Identifier{schema}.Sanitize()); e != nil {
				t.Fatal(e)
			}
			defer func() {
				admin.Exec(context.Background(), "DROP SCHEMA "+pgx.Identifier{schema}.Sanitize()+" CASCADE")
				admin.Close(context.Background())
			}()
			u, e := url.Parse(dsn)
			if e != nil {
				t.Fatal(e)
			}
			q := u.Query()
			q.Set("search_path", schema)
			u.RawQuery = q.Encode()
			pg, e := workflow.OpenPostgres(ctx, u.String())
			if e != nil {
				t.Fatal(e)
			}
			defer pg.Close()
			if e = pg.UpgradeArchiveMetadata(ctx); e != nil {
				t.Fatal(e)
			}
			index, e := search.Open(ctx, u.String())
			if e != nil {
				t.Fatal(e)
			}
			defer index.Close()
			source, e := archive.OpenMongo(ctx, uri, "factory_test", schema)
			if e != nil {
				t.Fatal(e)
			}
			defer source.Close()
			if e = source.EnsureMetadataSchema(); e != nil {
				t.Fatal(e)
			}
			ts, srv, i, c := captureServer(t, source, nil)
			srv.SetSearchStore(index)
			op := registry.Principal{Kind: registry.Operator}
			if e = c.MintProject(op, "p", "synthetic"); e != nil {
				t.Fatal(e)
			}
			provider := "synthetic"
			if route == "claude" {
				provider = "claude-code"
			}
			if route == "codex" {
				provider = "codex-hook-v1"
			}
			if route == "codex-v2" {
				provider = "codex-hook-v2"
			}
			if _, e = c.SetConsent(op, "p", provider, "capture", true); e != nil {
				t.Fatal(e)
			}
			if e = c.BeginArchiveMigration(op, "p", "g"); e != nil {
				t.Fatal(e)
			}
			root := t.TempDir()
			ledger, e := budget.Initialize(filepath.Join(root, "ledger"), budget.Policy{LiveCap: 1 << 30}, func() (budget.Sample, error) { return budget.LocalSample(root, 1<<30) })
			if e != nil {
				t.Fatal(e)
			}
			if e = c.AttachBudget(ledger); e != nil {
				t.Fatal(e)
			}
			if e = i.SetBudget(ledger); e != nil {
				t.Fatal(e)
			}
			if e = c.WithArchiveTransaction(op, "p", func(tx *control.ArchiveTransaction) error {
				return tx.FinishMigration(func(control.ArchiveState) error { return nil })
			}); e != nil {
				t.Fatal(e)
			}
			issue := func(id string, ops []string) map[string]string {
				t.Helper()
				code, g := do(t, "POST", ts.URL+"/v1/grants", opHdr(), map[string]any{"principal_id": id, "kind": "agent", "projects": []string{"p"}, "ops": ops, "secret": "fixture-" + id})
				if code != 201 {
					t.Fatal(code, g)
				}
				return map[string]string{"X-Principal-Id": id, "X-Grant-Epoch": itoa(int64(g["epoch"].(float64))), "X-Secret": "fixture-" + id}
			}
			writer := issue("writer", []string{"capture"})
			reader := issue("reader", []string{"search", "archive.query"})
			f := captureFixture{ts, c, i, writer}
			for n := 0; n < 2; n++ {
				code, b := scopedRequest(t, f, route, "p", writer)
				if code != 200 || b["accepted"] != float64(1) {
					t.Fatal(code, b)
				}
			}
			if _, e = srv.IndexOnce(); e != nil {
				t.Fatal(e)
			}
			code, b := do(t, "GET", ts.URL+"/v1/search/query?project=p&q=visible", reader, nil)
			if code != 200 || len(b["hits"].([]any)) != 1 {
				t.Fatal("search after idempotent capture", code, b)
			}
			hit := b["hits"].([]any)[0].(map[string]any)
			if hit["Project"] != "p" || hit["Provider"] != provider || hit["Text"] != "visible" {
				t.Fatal("wrong source", hit)
			}
			if code, _ := do(t, "GET", ts.URL+"/v1/search/query?project=p", writer, nil); code != 403 {
				t.Fatal("capture token read", code)
			}
			if code, _ := scopedRequest(t, f, route, "foreign", writer); code != 403 {
				t.Fatal("scope denial", code)
			}
			if e = c.RevokeGrant(op, "writer"); e != nil {
				t.Fatal(e)
			}
			if code, _ := scopedRequest(t, f, route, "p", writer); code != 403 {
				t.Fatal("revoked replay", code)
			}
			state, _, e := c.ArchiveState("p")
			if e != nil || state.CommittedOrdinal != 1 || state.Pending != nil {
				t.Fatal("source changed after denial", state, e)
			}
			checkpoint, found, e := index.Checkpoint("p")
			if e != nil || !found || !checkpoint.Complete || checkpoint.Ordinal != 1 {
				t.Fatal(checkpoint, found, e)
			}
		})
	}
}
