package api_test

import (
	"aifactory.local/storage/internal/archive"
	"aifactory.local/storage/internal/ingest"
	"encoding/json"
	"fmt"
	"net/http"
	"strings"
	"testing"
)

func TestSummaryReservedNamespaceRejectedBeforeWholeBatchIntake(t *testing.T) {
	for _, metadata := range []bool{false, true} {
		for _, route := range []string{"generic", "claude", "codex"} {
			t.Run(fmt.Sprintf("metadata=%v/%s", metadata, route), func(t *testing.T) {
				store := archive.NewMemStore()
				f := scopedFixture(t, metadata, nil, store)
				path := "/v1/capture"
				body := `{"project":"p","provider":"synthetic","source_instance":"fixture","messages":[{"session_id":"s","message_id":"ordinary-before-reserved","role":"user","text":"synthetic visible"},{"session_id":"s","message_id":"af-summary-v1/new","role":"user","text":"synthetic must not enter WAL"}]}`
				if route == "claude" {
					path += "/claude-code?project=p&source_instance=fixture"
					body = `{"type":"user","uuid":"af-summary-v1/new","sessionId":"s","message":{"role":"user","content":[{"type":"text","text":"synthetic must not enter WAL"}]}}`
				}
				if route == "codex" {
					path += "/codex-event?project=p&source_instance=fixture"
					body = `{"hook_event_name":"UserPromptSubmit","session_id":"s","turn_id":"af-summary-v1","prompt":"synthetic must not enter WAL"}`
				}
				before := summaryAcceptedCount(t, f.ing)
				req, err := http.NewRequest(http.MethodPost, f.ts.URL+path, strings.NewReader(body))
				if err != nil {
					t.Fatal(err)
				}
				for k, v := range f.writer {
					req.Header.Set(k, v)
				}
				response, err := http.DefaultClient.Do(req)
				if err != nil {
					t.Fatal(err)
				}
				defer response.Body.Close()
				var out map[string]any
				if err = json.NewDecoder(response.Body).Decode(&out); err != nil {
					t.Fatal(err)
				}
				records, err := store.Fetch("p")
				if err != nil || response.StatusCode != 409 || summaryAcceptedCount(t, f.ing) != before || len(records) != 0 {
					t.Fatal("reserved capture reached durable intake", response.StatusCode, len(records), err)
				}
				if _, exists := out["attempt_receipts"]; exists {
					t.Fatal("reserved namespace entered attempt intake")
				}
			})
		}
	}
}
func TestSummaryReservedNamespaceDoesNotHideHistoricalRowsOrRejectNearPrefixes(t *testing.T) {
	f := newSummaryHTTPFixture(t)
	for _, kind := range []archive.RecordType{archive.TypeMessage, archive.TypeSummary} {
		r := f.original.Record
		r.MessageID = archive.SessionExtractMessagePrefix + string(kind)
		r.Type = kind
		r.Text = "historical unmarked fixture"
		if err := f.store.Put(r); err != nil {
			t.Fatal(err)
		}
		if code, _ := agentQuery(t, f.http.URL, messagePath(r), "summary-reader", f.grantEpoch, "synthetic-reader-secret"); code != 200 {
			t.Fatal("historical reserved identity hidden", kind, code)
		}
		before := summaryAcceptedCount(t, f.intake)
		code, _ := do(t, http.MethodPost, f.http.URL+"/v1/capture", opHdr(), map[string]any{"project": "p", "provider": "synthetic", "source_instance": "i", "messages": []map[string]any{{"session_id": "s", "message_id": r.MessageID, "role": "user", "text": r.Text}}})
		actual, found, err := f.store.Lookup(r)
		if code != 409 || summaryAcceptedCount(t, f.intake) != before || err != nil || !found || actual != r {
			t.Fatal("historical collision retry changed stored bytes or reached WAL", kind, code, err)
		}
	}
	messages := []map[string]any{}
	for _, id := range []string{"x-af-summary-v1/a", "af-summary-v10/a", "AF-SUMMARY-V1/a"} {
		messages = append(messages, map[string]any{"session_id": "s", "message_id": id, "role": "user", "text": "near-prefix synthetic source"})
	}
	if code, body := do(t, http.MethodPost, f.http.URL+"/v1/capture", opHdr(), map[string]any{"project": "p", "provider": "synthetic", "source_instance": "i", "messages": messages}); code != 200 {
		t.Fatal("non-reserved identity refused", code, body)
	}
}

func summaryAcceptedCount(t *testing.T, i *ingest.Ingestor) int {
	t.Helper()
	n, err := i.AcceptedCount()
	if err != nil {
		t.Fatal(err)
	}
	return n
}
