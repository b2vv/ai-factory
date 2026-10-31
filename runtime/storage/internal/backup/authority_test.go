package backup

import (
	"aifactory.local/storage/internal/archive"
	"aifactory.local/storage/internal/control"
	"bytes"
	"path/filepath"
	"testing"
	"time"
)

func TestRestoreRequiresCurrentAuthorityBeforeAnyDestinationWrite(t *testing.T) {
	current, op := streamControl(t)
	source := archive.NewMemStore()
	workflow := newSnapshotFake()
	r := archive.Record{Project: "p", Provider: "synthetic", SourceInstance: "i", SessionID: "s", MessageID: "m", Text: "synthetic", ConsentEpoch: 1}
	if e := source.Put(r); e != nil {
		t.Fatal(e)
	}
	var snapshot bytes.Buffer
	if e := CreateStream(current, op, source, workflow, []string{"p"}, &snapshot); e != nil {
		t.Fatal(e)
	}
	missing, e := control.Open(filepath.Join(t.TempDir(), "missing-current-lineage"))
	if e != nil {
		t.Fatal(e)
	}
	defer missing.Close()
	destination := archive.NewMemStore()
	tasks := newSnapshotFake()
	if _, e = RestoreFile(missing, op, destination, tasks, bytes.NewReader(snapshot.Bytes()), time.Now()); e == nil {
		t.Fatal("data backup invented missing control authority")
	}
	if tasks.writes != 0 || len(destination.All("p")) != 0 {
		t.Fatal("restore wrote before authority verification")
	}
}
