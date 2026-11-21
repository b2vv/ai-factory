package api_test

import (
	"aifactory.local/storage/internal/archive"
	"aifactory.local/storage/internal/budget"
	"aifactory.local/storage/internal/control"
	"aifactory.local/storage/internal/registry"
	"path/filepath"
	"reflect"
	"testing"
)

func TestStartupRecoveryReconcilesOnlyProvenUnreservedIntent(t *testing.T) {
	for _, recovery := range []string{"source", "index"} {
		for _, kind := range []string{"archive-source-v2", "archive-index-v2", "unrelated-operation"} {
			t.Run(recovery+"/"+kind, func(t *testing.T) {
				_, srv, _, ctl := captureServer(t, archive.NewMemStore(), nil)
				op := registry.Principal{Kind: registry.Operator}
				if err := ctl.MintProject(op, "p", "fixture"); err != nil {
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
				evidence := budget.Evidence{Kind: kind, KeyHash: "unreserved-key", PayloadHash: "unreserved-payload"}
				if err = ctl.WithArchiveWriter(op, "p", func(*control.ArchiveTransaction) error { return ctl.ReserveIdentifiedExternal(evidence, 4096) }); err != nil {
					t.Fatal(err)
				}
				before := ledger.Snapshot()
				if recovery == "source" {
					err = srv.RecoverArchive()
				} else {
					err = srv.RecoverIndex()
				}
				if err != nil {
					t.Fatal(err)
				}
				after := ledger.Snapshot()
				matching := recovery == "source" && kind == "archive-source-v2" || recovery == "index" && kind == "archive-index-v2"
				if matching {
					if len(after.Pending) != 0 || after.Policy != before.Policy {
						t.Fatal("proven orphan not reconciled", after)
					}
				} else if !reflect.DeepEqual(before, after) {
					t.Fatal("foreign liability changed", before, after)
				}
			})
		}
	}
}
