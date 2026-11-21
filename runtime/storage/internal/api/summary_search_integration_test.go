//go:build integration

package api_test

import (
	"aifactory.local/storage/internal/archive"
	"aifactory.local/storage/internal/budget"
	"aifactory.local/storage/internal/config"
	"aifactory.local/storage/internal/control"
	"aifactory.local/storage/internal/registry"
	"aifactory.local/storage/internal/search"
	"aifactory.local/storage/internal/summary"
	"aifactory.local/storage/internal/workflow"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"github.com/jackc/pgx/v5"
	"net/url"
	"os"
	"path/filepath"
	"reflect"
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
			count, cycleErr := f.server.IndexOnce()
			if cycleErr != nil || count > 1 {
				t.Fatal("index exceeded one-record slice", count, cycleErr)
			}
			cp, found, err := index.Checkpoint("p")
			if err != nil {
				t.Fatal(err)
			}
			if n == 0 && (!found || cp.Ordinal != 1 || cp.Complete) {
				t.Fatal("first visible slice skipped uninspected tail", cp, found)
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

func TestSummaryMetadataIndexUsesFencedLedgerAndReportsRealProgress(t *testing.T) {
	for _, failLedger := range []bool{false, true} {
		t.Run(fmt.Sprint(failLedger), func(t *testing.T) {
			index := summarySearchStore(t)
			f := newSummaryHTTPFixture(t)
			f.server.SetSearchStore(index)
			preflightCalls := 0
			unavailable := errors.New("synthetic meter unavailable")
			f.server.SetUsageMeter(func() (config.Usage, error) { preflightCalls++; return config.Usage{}, unavailable })
			if failLedger {
				f.control.Budget().SetSampler(func() (budget.Sample, error) { return budget.Sample{}, unavailable })
			}
			n, advanced, err := f.server.IndexOnceProgress()
			cp, found, readErr := index.Checkpoint("p")
			if preflightCalls != 0 || readErr != nil {
				t.Fatal("metadata used redundant preflight", preflightCalls, readErr)
			}
			if failLedger {
				if !errors.Is(err, unavailable) || advanced || found {
					t.Fatal("failed ledger admitted projection", n, advanced, err, cp)
				}
				return
			}
			if err != nil || !advanced || n != 1 || !found || cp.Ordinal != 1 || cp.Complete {
				t.Fatal("metadata checkpoint progress", n, advanced, err, cp)
			}
			if n, advanced, err := f.server.IndexOnceProgress(); err != nil || n != 1 || !advanced {
				t.Fatal("tail failed", n, advanced, err)
			}
			if n, advanced, err := f.server.IndexOnceProgress(); err != nil || n != 0 || advanced {
				t.Fatal("idle checkpoint reported progress", n, advanced, err)
			}
		})
	}
}

func TestSummaryIndexLegacyStillRequiresItsUsagePreflight(t *testing.T) {
	index := summarySearchStore(t)
	_, server, _, ctl := captureServer(t, archive.NewMemStore(), nil)
	if err := ctl.MintProject(registry.Principal{Kind: registry.Operator}, "legacy", "synthetic"); err != nil {
		t.Fatal(err)
	}
	server.SetSearchStore(index)
	calls := 0
	unavailable := errors.New("synthetic legacy meter unavailable")
	server.SetUsageMeter(func() (config.Usage, error) { calls++; return config.Usage{}, unavailable })
	_, advanced, err := server.IndexOnceProgress()
	if !errors.Is(err, unavailable) || advanced || calls != 1 {
		t.Fatal("legacy bypassed metering or reported metadata progress", calls, advanced, err)
	}
}

func TestSummaryInitialEnablePreservesCompletePGThenIndexesOnlyNewSources(t *testing.T) {
	index := summarySearchStore(t)
	source := archive.NewMemStore()
	ts, server, intake, ctl := captureServer(t, source, nil)
	op := registry.Principal{Kind: registry.Operator}
	if err := ctl.MintProject(op, "p", "fixture"); err != nil {
		t.Fatal(err)
	}
	if _, err := ctl.SetConsent(op, "p", "synthetic", "capture", true); err != nil {
		t.Fatal(err)
	}
	if err := ctl.BeginArchiveMigration(op, "p", "g"); err != nil {
		t.Fatal(err)
	}
	root := t.TempDir()
	ledger, err := budget.Initialize(filepath.Join(root, "budget.bin"), budget.Policy{LiveCap: 1 << 30}, func() (budget.Sample, error) { return budget.LocalSample(root, 1<<30) })
	if err != nil {
		t.Fatal(err)
	}
	if err = ctl.AttachBudget(ledger); err != nil {
		t.Fatal(err)
	}
	if err = intake.SetBudget(ledger); err != nil {
		t.Fatal(err)
	}
	if err = ctl.WithArchiveTransaction(op, "p", func(tx *control.ArchiveTransaction) error {
		return tx.FinishMigration(func(control.ArchiveState) error { return nil })
	}); err != nil {
		t.Fatal(err)
	}
	server.SetSearchStore(index)
	capture := func(id string) {
		t.Helper()
		code, _ := do(t, "POST", ts.URL+"/v1/capture", opHdr(), map[string]any{"project": "p", "provider": "synthetic", "source_instance": "fixture", "messages": []map[string]any{{"session_id": "s", "message_id": id, "role": "user", "text": "synthetic " + id}}})
		if code != 200 {
			t.Fatal("capture", code)
		}
	}
	capture("historical")
	if n, _, err := server.IndexOnceProgress(); err != nil || n != 1 {
		t.Fatal(n, err)
	}
	before, found, err := index.Checkpoint("p")
	if err != nil || !found || !before.Complete || before.Ordinal != 1 {
		t.Fatal("initial complete checkpoint", before, err)
	}
	rows, _, err := index.Window("p", "", "")
	if err != nil || len(rows) != 1 {
		t.Fatal("original index rows", len(rows), err)
	}
	if _, err = ctl.SetConsent(op, "p", "synthetic", "summary", true); err != nil {
		t.Fatal(err)
	}
	if n, advanced, err := server.IndexOnceProgress(); err != nil || n != 0 || advanced {
		t.Fatal("first enable rebuilt original index", n, advanced, err)
	}
	after, _, err := index.Checkpoint("p")
	afterRows, _, readErr := index.Window("p", "", "")
	if err != nil || readErr != nil || after != before || !reflect.DeepEqual(rows, afterRows) {
		t.Fatal("first enable changed rows/token/checkpoint", before, after, err, readErr)
	}
	cfg := summary.DefaultConfig()
	cfg.IdleAfter = time.Nanosecond
	if err = server.ConfigureSummaries(cfg, summary.DefaultExtractOptions()); err != nil {
		t.Fatal(err)
	}
	if n, err := server.SummaryOnce(context.Background(), time.Now().UTC()); err != nil || n != 0 {
		t.Fatal("historical backfill", n, err)
	}
	capture("new")
	if n, err := server.SummaryOnce(context.Background(), time.Now().UTC()); err != nil || n != 1 {
		t.Fatal("future source not extracted", n, err)
	}
	for n := 0; n < 2; n++ {
		if count, _, err := server.IndexOnceProgress(); err != nil || count != 1 {
			t.Fatal("appended ordinal", count, err)
		}
	}
	done, _, err := index.Checkpoint("p")
	if err != nil || !done.Complete || done.Ordinal != 3 || done.ProjectionGeneration != before.ProjectionGeneration {
		t.Fatal("new records forced historical rebuild", done, err)
	}
	records, err := source.Fetch("p")
	if err != nil {
		t.Fatal(err)
	}
	derived := 0
	for _, record := range records {
		if record.Type == archive.TypeSummary {
			derived++
			var stored summary.StoredExtract
			if err := json.Unmarshal([]byte(record.Text), &stored); err != nil || len(stored.Document.Excerpts) != 1 || stored.Document.Excerpts[0].Identity.MessageID != "new" {
				t.Fatal("history entered derived coverage", err)
			}
		}
	}
	if derived != 1 {
		t.Fatal("derived count", derived)
	}
}
