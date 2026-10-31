package budget

import (
	"errors"
	"os"
	"path/filepath"
	"sync"
	"testing"
)

func sample(used *int64) Sampler {
	return func() (Sample, error) {
		return Sample{Components: map[string]int64{"local": *used}, Free: 1 << 40}, nil
	}
}
func TestDurableReservationExactFitRestartAndProof(t *testing.T) {
	var used int64
	path := filepath.Join(t.TempDir(), "budget.bin")
	l, e := Initialize(path, Policy{LiveCap: FileBytes + 100, Headroom: 100}, sample(&used))
	if e != nil {
		t.Fatal(e)
	}
	intent := Evidence{Kind: "synthetic", KeyHash: "key", PayloadHash: "payload"}
	if e = l.Reserve(intent, 101); !errors.Is(e, ErrCapacity) {
		t.Fatal(e)
	}
	if e = l.Reserve(intent, 100); e != nil {
		t.Fatal(e)
	}
	l.Close()
	l, e = Open(path, sample(&used))
	if e != nil {
		t.Fatal(e)
	}
	defer l.Close()
	if e = l.Reserve(Evidence{Kind: "other"}, 1); !errors.Is(e, ErrBlocked) {
		t.Fatal("restart forgot liability", e)
	}
	if e = l.Recover(func(Intent) (bool, error) { return false, nil }); !errors.Is(e, ErrBlocked) {
		t.Fatal("unknown outcome refunded", e)
	}
	used = 100
	if e = l.Recover(func(i Intent) (bool, error) { return i.Evidence == intent, nil }); e != nil {
		t.Fatal(e)
	}
	if e = l.Reserve(Evidence{Kind: "over"}, 1); !errors.Is(e, ErrCapacity) {
		t.Fatal("accepted past exact fit", e)
	}
}
func TestConcurrentAndExclusiveOwners(t *testing.T) {
	var used int64
	path := filepath.Join(t.TempDir(), "budget.bin")
	l, e := Initialize(path, Policy{LiveCap: FileBytes + 1, Headroom: 0}, sample(&used))
	if e != nil {
		t.Fatal(e)
	}
	defer l.Close()
	if other, e := Open(path, sample(&used)); e == nil {
		other.Close()
		t.Fatal("second accounting owner admitted")
	}
	var wg sync.WaitGroup
	var mu sync.Mutex
	won := 0
	for n := 0; n < 8; n++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			if l.Reserve(Evidence{Kind: "writer"}, 1) == nil {
				mu.Lock()
				won++
				mu.Unlock()
			}
		}()
	}
	wg.Wait()
	if won != 1 {
		t.Fatal("shared reservation overspent", won)
	}
}
func TestCorruptionNeverFallsBackAndPartialComponentsNeverRefund(t *testing.T) {
	var used int64
	path := filepath.Join(t.TempDir(), "budget.bin")
	l, e := Initialize(path, Policy{LiveCap: FileBytes + 1000}, sample(&used))
	if e != nil {
		t.Fatal(e)
	}
	l.SetSampler(func() (Sample, error) {
		return Sample{Components: map[string]int64{"db": 500, "local": 0}, Free: 1 << 40}, nil
	})
	if e = l.Refresh(); e != nil {
		t.Fatal(e)
	}
	l.SetSampler(sample(&used))
	if e = l.Refresh(); e != nil {
		t.Fatal(e)
	}
	if l.Snapshot().Components["db"] != 500 {
		t.Fatal("offline missing DB treated as empty")
	}
	l.Close()
	raw, e := os.ReadFile(path)
	if e != nil {
		t.Fatal(e)
	}
	raw[30] ^= 1
	if e = os.WriteFile(path, raw, 0600); e != nil {
		t.Fatal(e)
	}
	if other, e := Open(path, sample(&used)); !errors.Is(e, ErrBlocked) {
		if other != nil {
			other.Close()
		}
		t.Fatal("corrupt slot discarded", e)
	}
}
func TestMeasurementFailureKeepsPending(t *testing.T) {
	var used int64
	l, e := Initialize(filepath.Join(t.TempDir(), "budget.bin"), Policy{LiveCap: FileBytes + 100}, sample(&used))
	if e != nil {
		t.Fatal(e)
	}
	defer l.Close()
	if e = l.Reserve(Evidence{Kind: "write"}, 100); e != nil {
		t.Fatal(e)
	}
	l.SetSampler(func() (Sample, error) { return Sample{}, errors.New("unavailable") })
	if e = l.Finish(); e == nil {
		t.Fatal("unknown usage committed")
	}
	if len(l.Snapshot().Pending) != 1 {
		t.Fatal("lost reservation")
	}
}

func TestLocalInventoryCountsStagingAndRejectsLinks(t *testing.T) {
	dir := t.TempDir()
	if e := os.Mkdir(filepath.Join(dir, "stage"), 0700); e != nil {
		t.Fatal(e)
	}
	if e := os.WriteFile(filepath.Join(dir, "stage", "pending"), []byte("staging"), 0600); e != nil {
		t.Fatal(e)
	}
	snap, e := LocalSample(dir, 7)
	if e != nil || snap.Components["local"] != 7 {
		t.Fatal(snap, e)
	}
	if _, e = LocalSample(dir, 6); !errors.Is(e, ErrCapacity) {
		t.Fatal(e)
	}
	if e = os.Symlink(filepath.Join(dir, "stage", "pending"), filepath.Join(dir, "link")); e != nil {
		t.Fatal(e)
	}
	if _, e = LocalSample(dir, 100); e == nil {
		t.Fatal("nonregular state ignored")
	}
}

func TestRegisteredGeneratedFileAndStagingRemainBilledAfterRestart(t *testing.T) {
	root := t.TempDir()
	out := t.TempDir()
	target := filepath.Join(out, "workflow.md")
	if e := os.WriteFile(target, []byte("old"), 0600); e != nil {
		t.Fatal(e)
	}
	sample := func() (Sample, error) { return LocalSample(root, 1<<20) }
	l, e := Initialize(filepath.Join(root, "budget.bin"), Policy{LiveCap: 1 << 20}, sample)
	if e != nil {
		t.Fatal(e)
	}
	if e = RegisterPath(root, target, ".workflow-cutover-", l); e != nil {
		t.Fatal(e)
	}
	before := l.Snapshot().Components["managed-external"]
	if before != 3 {
		t.Fatal(before)
	}
	if e = l.Reserve(Evidence{Kind: "external", KeyHash: "synthetic"}, 5); e != nil {
		t.Fatal(e)
	}
	if e = os.WriteFile(filepath.Join(out, ".workflow-cutover-test"), []byte("newer"), 0600); e != nil {
		t.Fatal(e)
	}
	l.Close()
	l, e = Open(filepath.Join(root, "budget.bin"), sample)
	if e != nil {
		t.Fatal(e)
	}
	defer l.Close()
	if len(l.Snapshot().Pending) != 1 {
		t.Fatal("restart lost staging liability")
	}
	snap, e := sample()
	if e != nil || snap.Components["managed-external"] != 8 {
		t.Fatal(snap, e)
	}
	if e = l.Reserve(Evidence{Kind: "other"}, 1); !errors.Is(e, ErrBlocked) {
		t.Fatal(e)
	}
}
