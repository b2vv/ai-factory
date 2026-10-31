package ingest

import (
	"bytes"
	"encoding/json"
	"os"
	"path/filepath"
	"testing"

	"aifactory.local/storage/internal/archive"
	"aifactory.local/storage/internal/capture"
	"aifactory.local/storage/internal/config"
)

// Redaction must happen BEFORE the WAL, not only on the serve path: prohibited fields
// (hidden reasoning, secrets) must be absent from the WAL bytes on disk and from the stored
// archive records, not merely filtered out of a query response.
func TestRedactionBeforeWAL(t *testing.T) {
	const cot = "SECRET-CHAIN-OF-THOUGHT-9f3a"
	const key = "sk-LEAK-must-never-persist-0001"
	fx := capture.ProviderFixture{
		Provider: "synthetic", SourceInstance: "inst-1", Project: "p",
		Messages: []capture.FixtureMessage{{
			SessionID: "s", MessageID: "m1", Seq: 1, Role: "user", Text: "hello", Kind: "message",
			HiddenReasoning: cot, Secrets: map[string]string{"api_key": key},
		}},
	}
	recs, red := capture.Adapt(fx)
	if len(red) != 2 {
		t.Fatalf("expected hidden_reasoning + secrets redactions, got %v", red)
	}

	dir := filepath.Join(t.TempDir(), "wal")
	store := archive.NewMemStore()
	ing, err := Open(dir, config.NewAccountant(config.Default()), store)
	if err != nil {
		t.Fatal(err)
	}
	for i := range recs {
		recs[i].ConsentEpoch = 1
		if _, err := ing.Accept("k", recs[i], bigUsage()); err != nil {
			t.Fatal(err)
		}
	}
	if _, err := ing.Drain(); err != nil {
		t.Fatal(err)
	}
	ing.Close()

	forbidden := [][]byte{[]byte(cot), []byte(key)}

	// 1) Raw WAL files on disk must not contain the prohibited values.
	entries, _ := os.ReadDir(dir)
	for _, e := range entries {
		if e.IsDir() {
			continue
		}
		b, err := os.ReadFile(filepath.Join(dir, e.Name()))
		if err != nil {
			continue
		}
		for _, f := range forbidden {
			if bytes.Contains(b, f) {
				t.Fatalf("prohibited value leaked into WAL file %s", e.Name())
			}
		}
	}

	// 2) The stored archive records must not contain the prohibited values.
	for _, r := range store.All("p") {
		blob, _ := json.Marshal(r)
		for _, f := range forbidden {
			if bytes.Contains(blob, f) {
				t.Fatalf("prohibited value leaked into the stored archive record")
			}
		}
	}

	// 3) Structural guarantee: archive.Record has no field that could carry the prohibited
	// data (hidden reasoning / secrets are dropped by the adapter before a record exists), so
	// nothing downstream (WAL, Mongo, logs) can contain it. The handler logs no payloads.
}
