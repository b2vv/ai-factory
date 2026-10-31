package backup

import (
	"bytes"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"aifactory.local/storage/internal/archive"
	"aifactory.local/storage/internal/control"
	"aifactory.local/storage/internal/registry"
	"aifactory.local/storage/internal/workflow"
)

type snapshotFake struct {
	*workflow.MemStore
	rows   map[string][]workflow.Task
	writes int
}

func newSnapshotFake() *snapshotFake {
	return &snapshotFake{MemStore: workflow.NewMemStore(), rows: map[string][]workflow.Task{}}
}
func (s *snapshotFake) Snapshot(p string) ([]workflow.Task, error) { return s.rows[p], nil }
func (s *snapshotFake) Replace(p string, tasks []workflow.Task) error {
	s.rows[p] = append([]workflow.Task{}, tasks...)
	s.writes++
	return nil
}
func streamControl(t *testing.T) (*control.Durable, registry.Principal) {
	t.Helper()
	d, e := control.Initialize(filepath.Join(t.TempDir(), "control"))
	if e != nil {
		t.Fatal(e)
	}
	t.Cleanup(func() { d.Close() })
	op := registry.Principal{ID: "op", Kind: registry.Operator}
	if e = d.MintProject(op, "p", "synthetic"); e != nil {
		t.Fatal(e)
	}
	if _, e = d.SetConsent(op, "p", "synthetic", "capture", true); e != nil {
		t.Fatal(e)
	}
	return d, op
}
func TestStreamingBackupBeyondLegacyLimitAndCurrentBarrier(t *testing.T) {
	d, op := streamControl(t)
	a := archive.NewMemStore()
	p := newSnapshotFake()
	p.rows["p"] = []workflow.Task{{ID: "task", Version: 1, Fields: map[string]string{"kind": "task"}}}
	text := strings.Repeat("x", 1<<20)
	for n := 0; n < 40; n++ {
		session := "live"
		if n == 0 {
			session = "blocked"
		}
		if e := a.Put(archive.Record{Project: "p", Provider: "synthetic", SourceInstance: "fixture", SessionID: session, MessageID: fmt.Sprint(n), Seq: n, ConsentEpoch: 1, Text: text}); e != nil {
			t.Fatal(e)
		}
	}
	f, e := os.CreateTemp(t.TempDir(), "stream")
	if e != nil {
		t.Fatal(e)
	}
	defer f.Close()
	if e = CreateStream(d, op, a, p, []string{"p"}, f); e != nil {
		t.Fatal(e)
	}
	st, e := f.Stat()
	if e != nil || st.Size() <= MaxBytes {
		t.Fatal("not beyond legacy bound", st, e)
	}
	if _, e = d.DeleteSessionBarrier(op, "p", "blocked"); e != nil {
		t.Fatal(e)
	}
	target := archive.NewMemStore()
	tp := newSnapshotFake()
	result, e := RestoreFile(d, op, target, tp, f, time.Now())
	if e != nil || result.Restored != 39 || result.Withheld != 1 {
		t.Fatal(result, e)
	}
	if got := len(target.All("p")); got != 39 {
		t.Fatal(got)
	}
	if _, e = f.Seek(0, io.SeekStart); e != nil {
		t.Fatal(e)
	}
	meta, e := ReadWorkflowSnapshot(f, time.Now())
	if e != nil || len(meta.Projects) != 1 || len(meta.Projects[0].Archive) != 0 || len(meta.Projects[0].Tasks) != 1 {
		t.Fatal("B5 workflow metadata", e)
	}
	if _, e = f.Seek(0, io.SeekStart); e != nil {
		t.Fatal(e)
	}
	if _, e = inspectCreated(f, time.Now()); e != nil {
		t.Fatal("expiry compatibility", e)
	}
}
func TestStreamCorruptionAndTruncationBeforeAnyDestinationWrite(t *testing.T) {
	d, op := streamControl(t)
	a := archive.NewMemStore()
	p := newSnapshotFake()
	p.rows["p"] = []workflow.Task{{ID: "t", Version: 1}}
	if e := a.Put(archive.Record{Project: "p", Provider: "synthetic", SessionID: "s", MessageID: "m", ConsentEpoch: 1, Text: "keep"}); e != nil {
		t.Fatal(e)
	}
	var out bytes.Buffer
	if e := CreateStream(d, op, a, p, []string{"p"}, &out); e != nil {
		t.Fatal(e)
	}
	original := out.Bytes()
	corrupt := bytes.Replace(original, []byte("keep"), []byte("evil"), 1)
	for name, data := range map[string][]byte{"checksum": corrupt, "truncated": original[:len(original)-30], "trailing": append(append([]byte{}, original...), []byte("{}\n")...)} {
		t.Run(name, func(t *testing.T) {
			target := archive.NewMemStore()
			tp := newSnapshotFake()
			result, e := RestoreFile(d, op, target, tp, bytes.NewReader(data), time.Now())
			if e == nil || result.Restored != 0 || tp.writes != 0 || len(target.All("p")) != 0 {
				t.Fatal("modified targets before complete verification", result, e, tp.writes)
			}
		})
	}
	// Legacy format remains restorable through the same operational reader.
	var legacy bytes.Buffer
	if e := Create(d, op, a, p, []string{"p"}, &legacy); e != nil {
		t.Fatal(e)
	}
	if result, e := RestoreFile(d, op, archive.NewMemStore(), newSnapshotFake(), bytes.NewReader(legacy.Bytes()), time.Now()); e != nil || result.Restored != 1 {
		t.Fatal("legacy", result, e)
	}
}
func TestStreamExpiryAndStrictOrdering(t *testing.T) {
	d, op := streamControl(t)
	var out bytes.Buffer
	if e := CreateStream(d, op, archive.NewMemStore(), newSnapshotFake(), []string{"p"}, &out); e != nil {
		t.Fatal(e)
	}
	dir := filepath.Join(t.TempDir(), "backups")
	os.Mkdir(dir, 0700)
	os.WriteFile(filepath.Join(dir, "stream.backup"), out.Bytes(), 0600)
	r, e := OpenRepository(dir, 1<<20, 0)
	if e != nil {
		t.Fatal(e)
	}
	defer r.Close()
	result, e := r.Expire(time.Now().Add(31 * 24 * time.Hour))
	if e != nil || len(result.Removed) != 1 {
		t.Fatal(result, e)
	}
	if _, e = walkStream(strings.NewReader(streamMagic+strings.Repeat("x", maxFrameBytes+1)), time.Now(), false, nil); e == nil {
		t.Fatal("unbounded frame accepted")
	}
}

type restoreWriteFailure struct{ *archive.MemStore }

func (s *restoreWriteFailure) Put(archive.Record) error { return archive.ErrUnavailable }
func TestStreamPartialProjectIsNotReportedComplete(t *testing.T) {
	d, op := streamControl(t)
	source := archive.NewMemStore()
	p := newSnapshotFake()
	if e := source.Put(archive.Record{Project: "p", Provider: "synthetic", SessionID: "s", MessageID: "m", ConsentEpoch: 1}); e != nil {
		t.Fatal(e)
	}
	var raw bytes.Buffer
	if e := CreateStream(d, op, source, p, []string{"p"}, &raw); e != nil {
		t.Fatal(e)
	}
	targetPG := newSnapshotFake()
	result, e := RestoreFile(d, op, &restoreWriteFailure{archive.NewMemStore()}, targetPG, bytes.NewReader(raw.Bytes()), time.Now())
	if e == nil || result.Projects != 0 || result.Restored != 0 || targetPG.writes != 1 {
		t.Fatal("partial result dishonest", result, e, targetPG.writes)
	}
}
