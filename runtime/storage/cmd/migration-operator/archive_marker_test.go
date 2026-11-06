package main

import (
	"aifactory.local/storage/internal/budget"
	"aifactory.local/storage/internal/config"
	"aifactory.local/storage/internal/control"
	"aifactory.local/storage/internal/registry"
	"aifactory.local/storage/internal/search"
	"bytes"
	"os"
	"path/filepath"
	"reflect"
	"testing"
)

func TestMigrationIndexMarkerRecoversOnlyItsOwnIntent(t *testing.T) {
	for _, phase := range []string{"before-marker", "after-marker", "ready-unrelated", "absent-unrelated", "corrupt-marker"} {
		t.Run(phase, func(t *testing.T) {
			state := t.TempDir()
			d, e := control.InitializeBudgeted(state, config.Default())
			if e != nil {
				t.Fatal(e)
			}
			initialLedger, e := budget.Open(filepath.Join(state, "budget.bin"), func() (budget.Sample, error) { return budget.LocalSample(state, config.Default().LiveCapBytes) })
			if e != nil {
				t.Fatal(e)
			}
			if e = d.AttachBudget(initialLedger); e != nil {
				t.Fatal(e)
			}
			op := registry.Principal{Kind: registry.Operator}
			if e = d.MintProject(op, "p", "fixture"); e != nil {
				t.Fatal(e)
			}
			if e = d.BeginArchiveMigration(op, "p", "g"); e != nil {
				t.Fatal(e)
			}
			evidence := budget.Evidence{Kind: "archive-index-capability", KeyHash: archiveHash("archive-index-required"), PayloadHash: archiveHash("derived-archive-index-v1")}
			if phase == "ready-unrelated" || phase == "absent-unrelated" {
				evidence = budget.Evidence{Kind: "unrelated-fixture", KeyHash: "other", PayloadHash: "other"}
			}
			if e = d.WithArchiveWriter(op, "p", func(*control.ArchiveTransaction) error { return d.ReserveIdentifiedExternal(evidence, 4096) }); e != nil {
				t.Fatal(e)
			}
			if phase == "after-marker" || phase == "ready-unrelated" {
				if e = search.MarkRequired(state); e != nil {
					t.Fatal(e)
				}
			}
			marker := filepath.Join(state, "archive-index-required")
			if phase == "corrupt-marker" {
				if e = os.WriteFile(marker, []byte("partial"), 0600); e != nil {
					t.Fatal(e)
				}
			}
			before := d.Budget().Snapshot().Pending
			d.Close()
			// Real close/reopen: recovery cannot rely on an in-memory external reservation.
			d, e = control.Open(state)
			if e != nil {
				t.Fatal(e)
			}
			defer d.Close()
			l, e := budget.Open(filepath.Join(state, "budget.bin"), func() (budget.Sample, error) { return budget.LocalSample(state, 1<<30) })
			if e != nil {
				t.Fatal(e)
			}
			if e = d.AttachBudget(l); e != nil {
				t.Fatal(e)
			}
			e = ensureMigrationIndexMarker(d, op, state, "p")
			if phase == "absent-unrelated" || phase == "corrupt-marker" {
				if e == nil {
					t.Fatal("ambiguous marker accepted")
				}
				if !reflect.DeepEqual(before, d.Budget().Snapshot().Pending) {
					t.Fatal("foreign or unresolved liability released")
				}
				if phase == "absent-unrelated" {
					if _, e = os.Stat(marker); !os.IsNotExist(e) {
						t.Fatal("marker created before reservation", e)
					}
				} else {
					raw, e := os.ReadFile(marker)
					if e != nil || !bytes.Equal(raw, []byte("partial")) {
						t.Fatal("corrupt evidence replaced", e)
					}
				}
				return
			}
			if e != nil {
				t.Fatal(e)
			}
			ready, e := search.Required(state)
			if e != nil || !ready {
				t.Fatal(ready, e)
			}
			if phase == "ready-unrelated" {
				if !reflect.DeepEqual(before, d.Budget().Snapshot().Pending) {
					t.Fatal("ready schema consumed foreign intent")
				}
				return
			}
			if len(d.Budget().Snapshot().Pending) != 0 {
				t.Fatal("marker recovery left intent")
			}
			if e = ensureMigrationIndexMarker(d, op, state, "p"); e != nil || len(d.Budget().Snapshot().Pending) != 0 {
				t.Fatal("marker retry not idempotent", e)
			}
		})
	}
}
