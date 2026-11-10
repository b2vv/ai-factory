//go:build integration

package api_test

import (
	"aifactory.local/storage/internal/archive"
	"aifactory.local/storage/internal/control"
	"aifactory.local/storage/internal/registry"
	"aifactory.local/storage/internal/search"
	"aifactory.local/storage/internal/workflow"
	"context"
	"fmt"
	"github.com/jackc/pgx/v5"
	"net/url"
	"os"
	"testing"
	"time"
)

func summarySearchStore(t *testing.T) *search.Store {
	t.Helper()
	dsn := os.Getenv("PG_DSN")
	if dsn == "" {
		t.Skip("PG_DSN absent: actual summary search NOT_TESTED")
	}
	ctx := context.Background()
	admin, err := pgx.Connect(ctx, dsn)
	if err != nil {
		t.Fatal(err)
	}
	schema := fmt.Sprintf("summary_api_%d", time.Now().UnixNano())
	if _, err = admin.Exec(ctx, "CREATE SCHEMA "+pgx.Identifier{schema}.Sanitize()); err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { admin.Exec(ctx, "DROP SCHEMA "+pgx.Identifier{schema}.Sanitize()+" CASCADE"); admin.Close(ctx) })
	uri, err := url.Parse(dsn)
	if err != nil {
		t.Fatal(err)
	}
	q := uri.Query()
	q.Set("search_path", schema)
	uri.RawQuery = q.Encode()
	pg, err := workflow.OpenPostgres(ctx, uri.String())
	if err != nil {
		t.Fatal(err)
	}
	if err = pg.UpgradeArchiveMetadata(ctx); err != nil {
		pg.Close()
		t.Fatal(err)
	}
	pg.Close()
	index, err := search.Open(ctx, uri.String())
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(index.Close)
	return index
}

func TestSummarySearchAndRecentVerifySourcesAndCurrentConsent(t *testing.T) {
	index := summarySearchStore(t)
	f := newSummaryHTTPFixture(t)
	f.server.SetSearchStore(index)
	rebuild := func() {
		t.Helper()
		for n := 0; n < 8; n++ {
			if _, err := f.server.IndexOnce(); err != nil {
				t.Fatal("index cycle", err)
			}
			cp, found, err := index.Checkpoint("p")
			if err != nil {
				t.Fatal(err)
			}
			if found && cp.Complete && cp.Ordinal == 2 {
				return
			}
		}
		t.Fatal("bounded index never completed")
	}
	query := func(path string) (int, map[string]any) {
		return agentQuery(t, f.http.URL, path, "summary-reader", f.grantEpoch, "synthetic-reader-secret")
	}
	rebuild()
	for _, path := range []string{"/v1/search/query?project=p", "/v1/search/query?project=p&sort=recent&time_field=captured_at"} {
		if code, body := query(path); code != 200 || len(body["hits"].([]any)) != 2 {
			t.Fatal("valid summary search", path, code)
		}
	}
	for _, q := range []string{"local extract", "local\x00extract"} {
		code, body := query("/v1/search/query?project=p&q=" + url.QueryEscape(q))
		hits, ok := body["hits"].([]any)
		if code != 200 || !ok || len(hits) != 2 {
			t.Fatal("NUL token boundary or literal excerpts lost", code)
		}
	}
	t.Run("metadata-not-indexed", func(t *testing.T) {
		code, body := query("/v1/search/query?project=p&q=extractive")
		hits, ok := body["hits"].([]any)
		if code != 200 || !ok || len(hits) != 0 {
			t.Fatal("wrapper metadata leaked into terms", code)
		}
	})
	if _, err := f.control.SetConsent(registry.Principal{Kind: registry.Operator}, "p", "synthetic", "summary", false); err != nil {
		t.Fatal(err)
	}
	t.Run("normal-search-rechecks-before-rebuild", func(t *testing.T) {
		code, body := query("/v1/search/query?project=p")
		hits, ok := body["hits"].([]any)
		if code != 200 || !ok || len(hits) != 1 {
			t.Fatal("stale PG row bypassed summary revoke", code)
		}
	})
	rebuild()
	t.Run("recent-rechecks-after-current-policy-rebuild", func(t *testing.T) {
		code, body := query("/v1/search/query?project=p&sort=recent&time_field=captured_at")
		hits, ok := body["hits"].([]any)
		if code != 200 || !ok || len(hits) != 1 {
			t.Fatal("recent leaked revoked extract", code)
		}
	})
}

func TestSummaryDenseSearchAndRecentPaginationDoesNotSkipCandidates(t *testing.T) {
	index := summarySearchStore(t)
	f := newSummaryHTTPFixture(t)
	f.server.SetSearchStore(index)
	op := registry.Principal{Kind: registry.Operator}
	for n := 0; n < 10; n++ {
		r := f.original.Record
		r.MessageID = fmt.Sprintf("dense-manual-%d", n)
		r.Role = "assistant"
		r.Type = archive.TypeSummary
		r.Text = "Dense synthetic pagination marker"
		if err := f.control.WithArchiveTransaction(op, "p", func(tx *control.ArchiveTransaction) error {
			e, err := tx.Reserve(r, nil, false)
			if err != nil {
				return err
			}
			_, err = f.intake.CommitEnvelope(tx, e)
			return err
		}); err != nil {
			t.Fatal(err)
		}
	}
	complete := false
	for cycle := 0; cycle < 40; cycle++ {
		if _, err := f.server.IndexOnce(); err != nil {
			t.Fatal(err)
		}
		cp, found, err := index.Checkpoint("p")
		if err != nil {
			t.Fatal(err)
		}
		if found && cp.Complete && cp.Ordinal < 12 {
			t.Fatal("dense projection prematurely claimed complete cutoff", cp.Ordinal)
		}
		if found && cp.Complete && cp.Ordinal == 12 {
			complete = true
			break
		}
	}
	if !complete {
		t.Fatal("bounded projection never reached current cutoff")
	}
	for _, suffix := range []string{"", "&sort=recent&time_field=captured_at"} {
		seen := map[string]bool{}
		cursors := map[string]bool{}
		cursor := ""
		exhausted := false
		for page := 0; page < 20; page++ {
			path := "/v1/search/query?project=p&q=dense" + suffix
			if cursor != "" {
				path += "&cursor=" + url.QueryEscape(cursor)
			}
			code, body := agentQuery(t, f.http.URL, path, "summary-reader", f.grantEpoch, "synthetic-reader-secret")
			hits, ok := body["hits"].([]any)
			if code != 200 || !ok || len(hits) > 1 {
				t.Fatal("dense page bypassed one-summary proof bound", suffix, code, body)
			}
			for _, hit := range hits {
				r, ok := hit.(map[string]any)
				if !ok {
					t.Fatal("invalid hit")
				}
				id, ok := r["MessageID"].(string)
				if !ok || seen[id] {
					t.Fatal("repeated/malformed hit", id)
				}
				seen[id] = true
			}
			next, _ := body["next_cursor"].(string)
			if next == "" {
				exhausted = true
				break
			}
			if cursors[next] {
				t.Fatal("cursor cycle")
			}
			cursors[next] = true
			cursor = next
		}
		if !exhausted || len(seen) != 10 {
			t.Fatal("dense keyset lost candidates", suffix, exhausted, len(seen))
		}
	}
}
