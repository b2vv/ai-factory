package ingest

// F10 at the ingest layer: receipt state derivation across the lifecycle, including the two
// states that need the drain gate / archive presence (archive_committed vs quarantined) and the
// cross-project isolation guard. Driven directly so the monotone gate can quarantine a record.

import (
	"os"
	"path/filepath"
	"testing"

	"aifactory.local/storage/internal/archive"
	"aifactory.local/storage/internal/config"
)

func TestRecordStateLifecycleAndIsolation(t *testing.T) {
	d := t.TempDir()
	store := archive.NewMemStore()
	i, e := Open(d, config.NewAccountant(config.Default()), store)
	if e != nil {
		t.Fatal(e)
	}
	defer i.Close()
	u := config.Usage{FreeBytes: 1 << 40}

	rA := archive.Record{Project: "p", SourceInstance: "i", SessionID: "s", MessageID: "a", Type: archive.TypeMessage, Text: "x"}
	rB := archive.Record{Project: "p", SourceInstance: "i", SessionID: "s", MessageID: "b", Type: archive.TypeMessage, Text: "y"}
	keyA, keyB := archive.IdentityKey(rA), archive.IdentityKey(rB)
	if _, e := i.Accept(keyA, rA, u); e != nil {
		t.Fatal(e)
	}
	if _, e := i.Accept(keyB, rB, u); e != nil {
		t.Fatal(e)
	}

	// Drain, publishing A but QUARANTINING B (monotone gate denies message "b").
	if _, e := i.DrainGated(func(r archive.Record) bool { return r.MessageID != "b" }); e != nil {
		t.Fatal(e)
	}

	must := func(key, project, want string) {
		t.Helper()
		st, err := i.RecordState(key, project)
		if err != nil {
			t.Fatalf("RecordState(%q): %v", key, err)
		}
		if st.State != want {
			t.Fatalf("state for %q/%q = %q, want %q", key, project, st.State, want)
		}
	}

	must(keyA, "p", "archive_committed") // published
	must(keyB, "p", "quarantined")       // gate-denied, addressable but not in the archive
	must(keyA, "other", "not_found")     // cross-project isolation: no leak
	must("zzz", "p", "not_found")        // never accepted

	// A fresh accept with no drain is durable_accepted (pending).
	rC := archive.Record{Project: "p", SourceInstance: "i", SessionID: "s", MessageID: "c", Type: archive.TypeMessage, Text: "z"}
	if _, e := i.Accept(archive.IdentityKey(rC), rC, u); e != nil {
		t.Fatal(e)
	}
	must(archive.IdentityKey(rC), "p", "durable_accepted")
}

func TestProjectOfIdentityKey(t *testing.T) {
	r := archive.Record{Project: "proj-A", SourceInstance: "i", SessionID: "s", MessageID: "m"}
	if p, ok := projectOfIdentityKey(archive.IdentityKey(r)); !ok || p != "proj-A" {
		t.Fatalf("canonical key must yield its project: got %q ok=%v", p, ok)
	}
	// Legacy opaque delimiter key and garbage must fail closed (ok=false), so an isolation
	// decision based on it reports not_found rather than guessing a project.
	for _, bad := range []string{"p|i|s|m", "", "not-json", "{}"} {
		if _, ok := projectOfIdentityKey(bad); ok {
			t.Fatalf("non-identity key %q must not parse to a project", bad)
		}
	}
}

// The BLOCKED-journal fallback must apply the SAME cross-project isolation guard as the normal
// path (a corrupt journal must not become a cross-project existence oracle).
func TestRecordStateBlockedPathIsolation(t *testing.T) {
	d := t.TempDir()
	store := archive.NewMemStore()
	i, e := Open(d, config.NewAccountant(config.Default()), store)
	if e != nil {
		t.Fatal(e)
	}
	u := config.Usage{FreeBytes: 1 << 40}
	rP := archive.Record{Project: "p", SourceInstance: "i", SessionID: "s", MessageID: "mp", Type: archive.TypeMessage, Text: "x"}
	rQ := archive.Record{Project: "q", SourceInstance: "i", SessionID: "s", MessageID: "mq", Type: archive.TypeMessage, Text: "y"}
	keyP, keyQ := archive.IdentityKey(rP), archive.IdentityKey(rQ)
	if _, e := i.Accept(keyP, rP, u); e != nil {
		t.Fatal(e)
	}
	if _, e := i.Accept(keyQ, rQ, u); e != nil {
		t.Fatal(e)
	}
	i.Close()

	// Damage an accepted frame's payload on disk so recovery is BLOCKED (F13 preserve+quarantine):
	// flip a byte near the end of the data file (inside the last accepted frame).
	dataPath := filepath.Join(d, "data")
	b, err := os.ReadFile(dataPath)
	if err != nil {
		t.Fatal(err)
	}
	b[len(b)-6] ^= 0xFF
	if err := os.WriteFile(dataPath, b, 0o600); err != nil {
		t.Fatal(err)
	}

	i2, e := Open(d, config.NewAccountant(config.Default()), store)
	if e != nil {
		t.Fatal(e)
	}
	defer i2.Close()

	state := func(key, project string) string {
		st, err := i2.RecordState(key, project)
		if err != nil {
			t.Fatalf("RecordState(%q,%q): %v", key, project, err)
		}
		if st.State != "not_found" && !st.Blocked {
			t.Fatalf("journal must be BLOCKED for this test; state=%+v", st)
		}
		if st.State == "not_found" && st.Blocked {
			t.Fatalf("missing/foreign receipt leaks global blocked state: %+v", st)
		}
		return st.State
	}
	// keyP is in the intact validated prefix. The core guarantee: it is reported for its OWN
	// project but hidden (not_found) for another project even while the journal is BLOCKED —
	// without the guard, the cross-project query would leak its existence/state.
	if s := state(keyP, "p"); s == "not_found" {
		t.Fatalf("same-project P-under-p must report a state while BLOCKED, got not_found")
	}
	if s := state(keyP, "q"); s != "not_found" {
		t.Fatalf("cross-project P-under-q must be not_found while BLOCKED, got %q", s)
	}
	// A cross-project query for the damaged frame's key is also not_found (guard fires before
	// any region is searched, on the project mismatch alone).
	if s := state(keyQ, "p"); s != "not_found" {
		t.Fatalf("cross-project Q-under-p must be not_found while BLOCKED, got %q", s)
	}
}
