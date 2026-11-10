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
	"encoding/json"
	"errors"
	"fmt"
	"github.com/jackc/pgx/v5"
	"net/http"
	"net/url"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

func TestMetadataRuntimeIndexUsesCommittedSourceCheckpoint(t *testing.T) {
	dsn := os.Getenv("PG_DSN")
	if dsn == "" {
		t.Skip("PG_DSN absent: metadata runtime index NOT_TESTED")
	}
	ctx := context.Background()
	admin, err := pgx.Connect(ctx, dsn)
	if err != nil {
		t.Fatal(err)
	}
	schema := fmt.Sprintf("metadata_api_%d", time.Now().UnixNano())
	if _, err := admin.Exec(ctx, "CREATE SCHEMA "+pgx.Identifier{schema}.Sanitize()); err != nil {
		t.Fatal(err)
	}
	defer func() { admin.Exec(ctx, "DROP SCHEMA "+pgx.Identifier{schema}.Sanitize()+" CASCADE"); admin.Close(ctx) }()
	u, err := url.Parse(dsn)
	if err != nil {
		t.Fatal(err)
	}
	q := u.Query()
	q.Set("search_path", schema)
	u.RawQuery = q.Encode()
	pg, err := workflow.OpenPostgres(ctx, u.String())
	if err != nil {
		t.Fatal(err)
	}
	defer pg.Close()
	if err := pg.UpgradeArchiveMetadata(ctx); err != nil {
		t.Fatal(err)
	}
	index, err := search.Open(ctx, u.String())
	if err != nil {
		t.Fatal(err)
	}
	defer index.Close()
	source := &recentSource{MemStore: archive.NewMemStore()}
	ts, srv, i, ctl := captureServer(t, source, nil)
	srv.SetSearchStore(index)
	op := registry.Principal{Kind: registry.Operator}
	if err := ctl.MintProject(op, "p", "p"); err != nil {
		t.Fatal(err)
	}
	if _, err := ctl.SetConsent(op, "p", "synthetic", "capture", true); err != nil {
		t.Fatal(err)
	}
	if err := ctl.BeginArchiveMigration(op, "p", "g"); err != nil {
		t.Fatal(err)
	}
	root := t.TempDir()
	l, err := budget.Initialize(filepath.Join(root, "ledger"), budget.Policy{LiveCap: 1 << 30}, func() (budget.Sample, error) { return budget.LocalSample(root, 1<<30) })
	if err != nil {
		t.Fatal(err)
	}
	if err := ctl.AttachBudget(l); err != nil {
		t.Fatal(err)
	}
	if err := i.SetBudget(l); err != nil {
		t.Fatal(err)
	}
	if err := ctl.WithArchiveTransaction(op, "p", func(tx *control.ArchiveTransaction) error {
		return tx.FinishMigration(func(control.ArchiveState) error { return nil })
	}); err != nil {
		t.Fatal(err)
	}
	body := map[string]any{"project": "p", "provider": "synthetic", "source_instance": "i", "messages": []map[string]any{{"session_id": "s", "message_id": "m", "text": "needle"}}}
	if code, resp := do(t, http.MethodPost, ts.URL+"/v1/capture", opHdr(), body); code != 200 {
		t.Fatal(code, resp)
	}
	if n, err := srv.IndexOnce(); err != nil || n != 1 {
		t.Fatal(n, err)
	}
	checkpoint, found, err := index.Checkpoint("p")
	if err != nil || !found || !checkpoint.Complete || checkpoint.Ordinal != 1 || checkpoint.SourceGeneration != "g" {
		t.Fatal(checkpoint, found, err)
	}

	_, grant := do(t, http.MethodPost, ts.URL+"/v1/grants", opHdr(), map[string]any{"principal_id": "metadata-reader", "kind": "agent", "projects": []string{"p"}, "ops": []string{"archive.query", "search"}, "secret": "synthetic-only"})
	epoch := itoa(int64(grant["epoch"].(float64)))
	if code, body := agentQuery(t, ts.URL, "/v1/archive/freshness?project=p", "metadata-reader", epoch, "synthetic-only"); code != 200 || body["index_state"] != "caught_up" || body["capture_completeness"] != "unknown" {
		t.Fatal(code, body)
	}
	if code, _ := agentQuery(t, ts.URL, "/v1/archive/freshness?project=other", "metadata-reader", epoch, "synthetic-only"); code != 403 {
		t.Fatal("freshness scope leak", code)
	}

	if err := ctl.WithArchiveTransaction(op, "p", func(tx *control.ArchiveTransaction) error {
		return tx.ReserveProjection(control.ArchiveProjection{Action: "complete", Expected: checkpoint, Desired: checkpoint}, 1024)
	}); err != nil {
		t.Fatal(err)
	}
	if code, body := agentQuery(t, ts.URL, "/v1/archive/freshness?project=p", "metadata-reader", epoch, "synthetic-only"); code != 200 || body["index_state"] != "recovering" {
		t.Fatal("unfinished index intent reported fresh", code, body)
	}
	if err := srv.RecoverIndex(); err != nil {
		t.Fatal(err)
	}
	code, recent := agentQuery(t, ts.URL, "/v1/search/query?project=p&sort=recent&time_field=captured_at", "metadata-reader", epoch, "synthetic-only")
	if code != 200 || recent["time_field"] != "captured_at" || recent["total_exact"] != false || len(recent["hits"].([]any)) != 1 {
		t.Fatal("captured-time query", code, recent)
	}
	code, recent = agentQuery(t, ts.URL, "/v1/search/query?project=p&sort=recent", "metadata-reader", epoch, "synthetic-only")
	if code != 200 || recent["time_field"] != "source_event_time" || len(recent["hits"].([]any)) != 0 {
		t.Fatal("unknown source time was invented", code, recent)
	}
	if code, _ := agentQuery(t, ts.URL, "/v1/search/query?project=p&sort=recent&since=invalid", "metadata-reader", epoch, "synthetic-only"); code != 400 {
		t.Fatal("invalid since", code)
	}

	// Multiple raw pages and a later commit must not duplicate or inject a record
	// into the cursor's committed upper bound.
	add := func(id string) {
		t.Helper()
		if err := ctl.WithArchiveTransaction(op, "p", func(tx *control.ArchiveTransaction) error {
			e, err := tx.Reserve(archive.Record{Project: "p", Provider: "synthetic", SourceInstance: "i", SessionID: "s", MessageID: id, Text: "needle", ConsentEpoch: 1}, nil, false)
			if err != nil {
				return err
			}
			_, err = i.CommitEnvelope(tx, e)
			return err
		}); err != nil {
			t.Fatal(err)
		}
	}
	for n := 0; n < 103; n++ {
		add(fmt.Sprintf("page-%03d", n))
	}
	for n := 0; n < 103; n++ {
		if count, err := srv.IndexOnce(); err != nil || count > 1 {
			t.Fatal("incremental index slice", count, err)
		}
		if n == 1 {
			if code, _ := agentQuery(t, ts.URL, "/v1/search/query?project=p&sort=recent&time_field=captured_at&q=needle", "metadata-reader", epoch, "synthetic-only"); code != 503 {
				t.Fatal("unfinished incremental index claimed query readiness", code)
			}
		}
	}
	code, first := agentQuery(t, ts.URL, "/v1/search/query?project=p&sort=recent&time_field=captured_at&q=needle", "metadata-reader", epoch, "synthetic-only")
	if code != 200 || len(first["hits"].([]any)) != 100 || first["next_cursor"] == "" {
		t.Fatal("first page", code, first)
	}
	cursor := first["next_cursor"].(string)
	add("late")
	if _, err := srv.IndexOnce(); err != nil {
		t.Fatal(err)
	}
	path := "/v1/search/query?project=p&sort=recent&time_field=captured_at&q=needle&cursor=" + url.QueryEscape(cursor)
	code, second := agentQuery(t, ts.URL, path, "metadata-reader", epoch, "synthetic-only")
	if code != 200 || len(second["hits"].([]any)) != 4 || second["next_cursor"] != "" {
		t.Fatal("continuation", code, second)
	}
	seen := map[string]bool{}
	for _, hit := range append(first["hits"].([]any), second["hits"].([]any)...) {
		id := hit.(map[string]any)["MessageID"].(string)
		if seen[id] || id == "late" {
			t.Fatal("unstable membership", id)
		}
		seen[id] = true
	}
	if code, _ := agentQuery(t, ts.URL, path+"&provider=synthetic", "metadata-reader", epoch, "synthetic-only"); code != 400 {
		t.Fatal("cursor filter mismatch", code)
	}
	if code, _ := agentQuery(t, ts.URL, "/v1/archive/query?project=p&q=needle&cursor="+url.QueryEscape(cursor), "metadata-reader", epoch, "synthetic-only"); code != 400 {
		t.Fatal("cross-route cursor accepted", code)
	}

	// Every raw page remains traversable when query/provider filters yield no hits.
	for _, filter := range []string{"q=absent", "provider=other"} {
		route := "/v1/search/query?project=p&sort=recent&time_field=captured_at&" + filter
		code, empty := agentQuery(t, ts.URL, route, "metadata-reader", epoch, "synthetic-only")
		if code != 200 || len(empty["hits"].([]any)) != 0 || empty["next_cursor"] == "" {
			t.Fatal("filtered first page", code, empty)
		}
		code, terminal := agentQuery(t, ts.URL, route+"&cursor="+url.QueryEscape(empty["next_cursor"].(string)), "metadata-reader", epoch, "synthetic-only")
		if code != 200 || len(terminal["hits"].([]any)) != 0 || terminal["next_cursor"] != "" {
			t.Fatal("filtered terminal page", code, terminal)
		}
	}
	// The index cannot substitute missing or changed authoritative source bytes.
	for _, mode := range []string{"missing", "metadata", "payload", "error"} {
		source.mode = mode
		code, result := agentQuery(t, ts.URL, "/v1/search/query?project=p&sort=recent&time_field=captured_at", "metadata-reader", epoch, "synthetic-only")
		raw, _ := json.Marshal(result)
		if strings.Contains(string(raw), "PRIVATE_BACKEND") {
			t.Fatal("backend details leaked")
		}
		if mode == "error" {
			if code != 503 {
				t.Fatal(mode, code, result)
			}
		} else if code != 200 || result["incomplete"] != true || len(result["hits"].([]any)) != 0 || len(result["snippets"].([]any)) != 0 {
			t.Fatal(mode, code, result)
		}
	}
	source.mode = ""

	// Byte-limited pages must resume before the first unserved record.
	for n := 0; n < 3; n++ {
		if err := ctl.WithArchiveTransaction(op, "p", func(tx *control.ArchiveTransaction) error {
			e, err := tx.Reserve(archive.Record{Project: "p", Provider: "synthetic", SourceInstance: "i", SessionID: "s", MessageID: fmt.Sprintf("large-%d", n), Text: strings.Repeat("x", 3<<20), ConsentEpoch: 1}, nil, false)
			if err != nil {
				return err
			}
			_, err = i.CommitEnvelope(tx, e)
			return err
		}); err != nil {
			t.Fatal(err)
		}
	}
	for n := 0; n < 3; n++ {
		if _, err := srv.IndexOnce(); err != nil {
			t.Fatal(err)
		}
	}
	route := "/v1/search/query?project=p&sort=recent&time_field=captured_at"
	continuation := ""
	all := map[string]bool{}
	for page := 0; page < 5; page++ {
		target := route
		if continuation != "" {
			target += "&cursor=" + url.QueryEscape(continuation)
		}
		code, result := agentQuery(t, ts.URL, target, "metadata-reader", epoch, "synthetic-only")
		if code != 200 {
			t.Fatal("byte page", code, result)
		}
		hits := result["hits"].([]any)
		if page == 0 && len(hits) != 2 {
			t.Fatal("expected byte-limited prefix", len(hits))
		}
		bytes := 0
		for _, hit := range hits {
			raw, _ := json.Marshal(hit)
			bytes += len(raw)
			id := hit.(map[string]any)["MessageID"].(string)
			if all[id] {
				t.Fatal("duplicate byte continuation", id)
			}
			all[id] = true
		}
		if bytes > archive.ScanBytes {
			t.Fatal("hit byte bound", bytes)
		}
		continuation = result["next_cursor"].(string)
		if continuation == "" {
			break
		}
	}
	if continuation != "" || len(all) != 108 {
		t.Fatal("lost byte-limited records", len(all), continuation != "")
	}
	// Revocation during lookup must fence both full payloads and snippets.
	source.before = func() {
		source.before = nil
		code, _ := do(t, http.MethodPost, ts.URL+"/v1/grants/revoke", opHdr(), map[string]string{"principal_id": "metadata-reader"})
		if code != 200 {
			t.Error(code)
		}
	}
	code, revoked := agentQuery(t, ts.URL, "/v1/search/query?project=p&sort=recent&time_field=captured_at", "metadata-reader", epoch, "synthetic-only")
	if code != 403 {
		t.Fatal("final grant fence", code, revoked)
	}
	_, grant = do(t, http.MethodPost, ts.URL+"/v1/grants", opHdr(), map[string]any{"principal_id": "metadata-reader", "kind": "agent", "projects": []string{"p"}, "ops": []string{"archive.query", "search"}, "secret": "synthetic-only"})
	epoch = itoa(int64(grant["epoch"].(float64)))
	// A policy mutation during lookup invalidates the page before any data leaves.
	source.before = func() {
		source.before = nil
		if _, err := ctl.DeleteSessionBarrier(op, "p", "s"); err != nil {
			t.Error(err)
		}
	}
	if code, _ := agentQuery(t, ts.URL, "/v1/search/query?project=p&sort=recent&time_field=captured_at", "metadata-reader", epoch, "synthetic-only"); code != 409 {
		t.Fatal("final policy fence", code)
	}
	if _, err := ctl.DeleteSessionBarrier(op, "p", "s"); err != nil {
		t.Fatal(err)
	}

	if code, body := agentQuery(t, ts.URL, "/v1/archive/freshness?project=p", "metadata-reader", epoch, "synthetic-only"); code != 200 || body["index_state"] != "behind" {
		t.Fatal("stale policy reported fresh", code, body)
	}
	currentState, _, err := ctl.ArchiveState("p")
	if err != nil {
		t.Fatal(err)
	}
	for n := int64(0); n < currentState.CommittedOrdinal; n++ {
		if count, err := srv.IndexOnce(); err != nil || count > 1 {
			t.Fatal("hidden policy rebuild slice", count, err)
		}
	}
	next, _, err := index.Checkpoint("p")
	if err != nil || !next.Complete || next.ProjectionGeneration == checkpoint.ProjectionGeneration {
		t.Fatal(next, err)
	}

	if code, _ := agentQuery(t, ts.URL, path, "metadata-reader", epoch, "synthetic-only"); code != 409 {
		t.Fatal("rebuilt cursor accepted", code)
	}
	refs, _, err := index.Window("p", "needle", "")
	if err != nil || len(refs) != 0 {
		t.Fatal(refs, err)
	}
}

// Fault injection at the authoritative read boundary, after index selection.
type recentSource struct {
	*archive.MemStore
	before func()
	mode   string
}

func (s *recentSource) LookupEnvelope(r archive.Record) (archive.Envelope, bool, error) {
	if s.before != nil {
		s.before()
	}
	e, found, err := s.MemStore.LookupEnvelope(r)
	switch s.mode {
	case "missing":
		return e, false, nil
	case "metadata":
		e.Metadata.Ordinal++
	case "payload":
		e.Record.Text = "PRIVATE_BACKEND"
	case "error":
		return e, false, errors.New("PRIVATE_BACKEND")
	}
	return e, found, err
}
