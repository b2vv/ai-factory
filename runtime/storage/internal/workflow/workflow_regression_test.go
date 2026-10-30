package workflow

// Regression test for interim-review finding IR4: a workflow write must not commit to
// the structured store after the authority cutover has superseded the writer's epoch.
// The defect is an interleaving between the epoch check and the storage commit, so the
// test drives a real concurrent cutover against a store whose commit is paused.

import (
	"sync"
	"sync/atomic"
	"testing"
	"time"

	"aifactory.local/storage/internal/registry"
)

// hookStore is a fake PG store whose CAS pauses on first use so the test can attempt a
// concurrent cutover while a commit is in flight.
type hookStore struct {
	mu       sync.Mutex
	up       bool
	tasks    map[string]Task
	casEnter chan struct{}
	release  chan struct{}
	once     sync.Once
	flipped  *int32
	observed *int32 // set to the value of *flipped at the instant the commit lands
}

func (s *hookStore) Available() bool { return s.up }

func (s *hookStore) Get(project, id string) (Task, bool) {
	s.mu.Lock()
	defer s.mu.Unlock()
	t, ok := s.tasks[project+"/"+id]
	return t, ok
}

func (s *hookStore) CAS(project string, t Task, expectedVersion int64) error {
	// Pause the very first commit so a cutover can race it.
	s.once.Do(func() {
		s.casEnter <- struct{}{}
		<-s.release
		atomic.StoreInt32(s.observed, atomic.LoadInt32(s.flipped))
	})
	s.mu.Lock()
	defer s.mu.Unlock()
	cur := s.tasks[project+"/"+t.ID]
	if cur.Version != expectedVersion {
		return ErrStaleVersion
	}
	s.tasks[project+"/"+t.ID] = t
	return nil
}

func TestIR4_WriteMustNotCommitAfterCutover(t *testing.T) {
	op := registry.Principal{ID: "op", Kind: registry.Operator}
	reg := registry.New()
	if err := reg.MintProject(op, "p", "P"); err != nil {
		t.Fatal(err)
	}

	var flipped, observed int32
	store := &hookStore{
		up:       true,
		tasks:    map[string]Task{},
		casEnter: make(chan struct{}),
		release:  make(chan struct{}),
		flipped:  &flipped,
		observed: &observed,
	}
	mgr := New(reg, store)

	// Opt the project into PG ownership: authority becomes postgres at epoch 2.
	rcpt, err := mgr.EnablePG(op, "p", "export-hash")
	if err != nil {
		t.Fatalf("EnablePG: %v", err)
	}
	writerEpoch := rcpt.NewEpoch

	// A legitimate write starts and pauses inside the store commit.
	var writeErr error
	writeDone := make(chan struct{})
	go func() {
		writeErr = mgr.Write("p", "task", 0, writerEpoch, map[string]string{"value": "late"})
		close(writeDone)
	}()
	<-store.casEnter

	// Concurrently, an operator cuts authority back to Markdown (bumping the epoch).
	flipDone := make(chan struct{})
	go func() {
		_, _ = mgr.DisablePG(op, "p", "verified-export-hash")
		atomic.StoreInt32(&flipped, 1)
		close(flipDone)
	}()

	// Give the cutover a chance to complete. With correct commit-time fencing it
	// cannot proceed while the commit holds authority; on the buggy tree it flips here.
	time.Sleep(150 * time.Millisecond)
	close(store.release)
	<-writeDone
	<-flipDone

	if atomic.LoadInt32(&observed) != 0 {
		t.Fatalf("IR4: workflow write committed after the authority cutover superseded its epoch")
	}
	if writeErr != nil {
		t.Fatalf("IR4: the pre-cutover write should still commit legitimately, got err=%v", writeErr)
	}
}
