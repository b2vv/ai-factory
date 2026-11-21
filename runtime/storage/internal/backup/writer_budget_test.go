package backup

import (
	"aifactory.local/storage/internal/archive"
	"aifactory.local/storage/internal/registry"
	"aifactory.local/storage/internal/workflow"
	"bytes"
	"errors"
	"os"
	"path/filepath"
	"testing"
	"time"
)

func TestWriterBudgetDenialPrecedesEveryDestinationWrite(t *testing.T) {
	for _, kind := range []string{"restore-v1", "restore-v2", "cutover-import"} {
		t.Run(kind, func(t *testing.T) {
			d, op := streamControl(t)
			source := archive.NewMemStore()
			tasks := newSnapshotFake()
			tasks.rows["p"] = []workflow.Task{{ID: "task", Version: 1, Fields: map[string]string{"title": "synthetic"}}}
			record := archive.Record{Project: "p", Provider: "synthetic", SourceInstance: "fixture", SessionID: "s", MessageID: "m", ConsentEpoch: 1, Text: "synthetic"}
			if e := source.Put(record); e != nil {
				t.Fatal(e)
			}
			var raw bytes.Buffer
			if kind == "restore-v1" {
				if e := Create(d, op, source, tasks, []string{"p"}, &raw); e != nil {
					t.Fatal(e)
				}
			}
			if kind == "restore-v2" {
				if e := CreateStream(d, op, source, tasks, []string{"p"}, &raw); e != nil {
					t.Fatal(e)
				}
			}
			target := archive.NewMemStore()
			targetTasks := newSnapshotFake()
			checks := 0
			d.SetCapacityCheck(func(int64) error { checks++; return errors.New("synthetic shared budget exhausted") })
			var e error
			switch kind {
			case "restore-v1":
				_, e = Restore(d, op, target, targetTasks, bytes.NewReader(raw.Bytes()), time.Now())
			case "restore-v2":
				_, e = RestoreFile(d, op, target, targetTasks, bytes.NewReader(raw.Bytes()), time.Now())
			case "cutover-import":
				doc, err := workflow.Document(tasks.rows["p"])
				if err != nil {
					t.Fatal(err)
				}
				path := filepath.Join(t.TempDir(), "workflow.md")
				if err = os.WriteFile(path, doc, 0600); err != nil {
					t.Fatal(err)
				}
				_, e = workflow.Cutover(d, targetTasks, op, "p", path, digest(doc), registry.OwnerPostgres)
			}
			if n := len(target.All("p")); e == nil || n != 0 || targetTasks.writes != 0 {
				t.Fatalf("budget denial did not precede writes: checks=%d archive=%d workflow_writes=%d error=%v", checks, n, targetTasks.writes, e)
			}
		})
	}
}
