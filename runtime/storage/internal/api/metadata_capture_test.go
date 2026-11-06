package api_test

import (
	"aifactory.local/storage/internal/archive"
	"aifactory.local/storage/internal/budget"
	"aifactory.local/storage/internal/control"
	"aifactory.local/storage/internal/registry"
	"net/http"
	"net/url"
	"path/filepath"
	"reflect"
	"testing"
)

func TestMetadataCaptureRefusesIncompleteMigrationThenCommits(t *testing.T) {
	source := archive.NewMemStore()
	ts, srv, i, ctl := captureServer(t, source, nil)
	op := registry.Principal{Kind: registry.Operator}
	if err := ctl.MintProject(op, "p", "fixture"); err != nil {
		t.Fatal(err)
	}
	if _, err := ctl.SetConsent(op, "p", "synthetic", "capture", true); err != nil {
		t.Fatal(err)
	}
	code, grant := do(t, http.MethodPost, ts.URL+"/v1/grants", opHdr(), map[string]any{"principal_id": "fixture-reader", "kind": "agent", "projects": []string{"p"}, "ops": []string{"archive.query"}, "secret": "fixture-secret"})
	if code != http.StatusCreated {
		t.Fatal("fixture grant", code, grant)
	}
	epoch := itoa(int64(grant["epoch"].(float64)))
	if err := ctl.BeginArchiveMigration(op, "p", "g"); err != nil {
		t.Fatal(err)
	}
	root := t.TempDir()
	l, err := budget.Initialize(filepath.Join(root, "budget.bin"), budget.Policy{LiveCap: 1 << 30}, func() (budget.Sample, error) { return budget.LocalSample(root, 1<<30) })
	if err != nil {
		t.Fatal(err)
	}
	if err := ctl.AttachBudget(l); err != nil {
		t.Fatal(err)
	}
	if err := i.SetBudget(l); err != nil {
		t.Fatal(err)
	}
	body := map[string]any{"project": "p", "provider": "synthetic", "source_instance": "i", "messages": []map[string]any{{"session_id": "s", "message_id": "m", "text": "original"}}}
	if code, resp := do(t, http.MethodPost, ts.URL+"/v1/capture", opHdr(), body); code != 503 {
		t.Fatal("incomplete migration accepted", code)
	} else if receipts, ok := resp["receipts"].([]any); !ok || len(receipts) != 0 || resp["accepted"] != float64(0) {
		t.Fatal("unaccepted operation claimed durable receipts", resp)
	}
	attemptKey := archive.IdentityKey(archive.Record{Project: "p", SourceInstance: "i", SessionID: "s", MessageID: "m"})
	if code, resp := agentQuery(t, ts.URL, "/v1/ingest/"+url.PathEscape(attemptKey)+"?project=p", "fixture-reader", epoch, "fixture-secret"); code != 200 || resp["state"] != "failed" || resp["observation"] != "ephemeral_request_10m" {
		t.Fatal("failed capture observation lost", code, resp)
	}
	if records, err := source.Fetch("p"); err != nil || len(records) != 0 {
		t.Fatal(records, err)
	}
	if err := ctl.WithArchiveTransaction(op, "p", func(tx *control.ArchiveTransaction) error {
		return tx.FinishMigration(func(control.ArchiveState) error { return nil })
	}); err != nil {
		t.Fatal(err)
	}
	for attempt := 0; attempt < 2; attempt++ {
		if code, resp := do(t, http.MethodPost, ts.URL+"/v1/capture", opHdr(), body); code != 200 {
			t.Fatal(code, resp)
		} else {
			expected := archive.IdentityKey(archive.Record{Project: "p", SourceInstance: "i", SessionID: "s", MessageID: "m"})
			if resp["accepted"] != float64(1) || resp["committed"] != float64(1) || !reflect.DeepEqual(resp["receipts"], []any{expected}) {
				t.Fatal("durable acceptance receipt mismatch", resp)
			}
		}
	}
	e, found, err := source.LookupEnvelope(archive.Record{Project: "p", SourceInstance: "i", SessionID: "s", MessageID: "m"})
	if err != nil || !found || e.Version != 2 || e.Metadata.CapturedAt == nil || e.Metadata.SourceEventTime != nil || e.Metadata.Ordinal != 1 {
		t.Fatal(e, found, err)
	}
	state, _, err := ctl.ArchiveState("p")
	if err != nil || state.CommittedOrdinal != 1 || state.NextOrdinal != 2 {
		t.Fatal(state, err)
	}
	timed := map[string]any{"project": "p", "provider": "synthetic", "source_instance": "i", "messages": []map[string]any{{"session_id": "s", "message_id": "timed", "text": "timed", "source_event_time": "2026-11-05T10:00:00.123456789Z"}}}
	if code, resp := do(t, http.MethodPost, ts.URL+"/v1/capture", opHdr(), timed); code != 200 {
		t.Fatal(code, resp)
	}
	actual, found, err := source.LookupEnvelope(archive.Record{Project: "p", SourceInstance: "i", SessionID: "s", MessageID: "timed"})
	if err != nil || !found || actual.Metadata.SourceEventTime == nil {
		t.Fatal("event time absent", actual, err)
	}
	timed["messages"] = []map[string]any{{"session_id": "s", "message_id": "timed", "text": "timed", "source_event_time": "2026-11-05T11:00:00.123456789+01:00"}}
	if code, resp := do(t, http.MethodPost, ts.URL+"/v1/capture", opHdr(), timed); code != 200 {
		t.Fatal("equivalent UTC retry", code, resp)
	}
	timed["messages"] = []map[string]any{{"session_id": "s", "message_id": "timed", "text": "timed", "source_event_time": "2026-11-05T10:00:01Z"}}
	if code, _ := do(t, http.MethodPost, ts.URL+"/v1/capture", opHdr(), timed); code != 409 {
		t.Fatal("conflicting event time", code)
	}

	// Leave another operation accepted, then recover without any producer retry.
	r := archive.Record{Project: "p", Provider: "synthetic", SourceInstance: "i", SessionID: "s", MessageID: "pending", Text: "pending", ConsentEpoch: e.Record.ConsentEpoch}
	if err := ctl.WithArchiveTransaction(op, "p", func(tx *control.ArchiveTransaction) error {
		envelope, err := tx.Reserve(r, nil, false)
		if err != nil {
			return err
		}
		_, err = i.AcceptEnvelope(envelope)
		return err
	}); err != nil {
		t.Fatal(err)
	}
	if _, err := srv.DrainOnce(); err != nil {
		t.Fatal("metadata background recovery", err)
	}
	if got, found, err := source.LookupEnvelope(r); err != nil || !found || got.Record != r {
		t.Fatal(got, found, err)
	}

	body["messages"] = []map[string]any{{"session_id": "s", "message_id": "m", "text": "changed"}}
	if code, _ := do(t, http.MethodPost, ts.URL+"/v1/capture", opHdr(), body); code != 409 {
		t.Fatal("changed duplicate", code)
	}
	if _, err := ctl.DeleteSessionBarrier(op, "p", "deleted"); err != nil {
		t.Fatal(err)
	}
	body["messages"] = []map[string]any{{"session_id": "fresh", "message_id": "visible", "text": "visible"}, {"session_id": "deleted", "message_id": "hidden", "text": "must never be published"}}
	if code, resp := do(t, http.MethodPost, ts.URL+"/v1/capture", opHdr(), body); code != 409 {
		t.Fatal("deleted session accepted", code, resp)
	}
	if _, found, err := source.LookupEnvelope(archive.Record{Project: "p", SourceInstance: "i", SessionID: "deleted", MessageID: "hidden"}); err != nil || found {
		t.Fatal("deleted session resurrected", found, err)
	}
	if _, found, err := source.LookupEnvelope(archive.Record{Project: "p", SourceInstance: "i", SessionID: "fresh", MessageID: "visible"}); err != nil || !found {
		t.Fatal("accepted prefix lost", found, err)
	}

}
