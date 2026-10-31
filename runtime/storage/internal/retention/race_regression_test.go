package retention

// R7 regression: the barrier log is read (Serve/barred/Barriers) concurrently with operator
// installs (DeleteProject/DeleteSession). With the Manager's RWMutex this must be race-free.
// Run under `go test -race` to be meaningful.

import (
	"sync"
	"testing"

	"aifactory.local/storage/internal/archive"
	"aifactory.local/storage/internal/registry"
)

func TestRetentionBarrierConcurrentReadWriteNoRace(t *testing.T) {
	m := New(registry.New())
	rec := archive.Record{Project: "p", SessionID: "s", Provider: "synthetic"}
	var wg sync.WaitGroup
	// Writers: install barriers concurrently.
	for w := 0; w < 4; w++ {
		wg.Add(1)
		go func(w int) {
			defer wg.Done()
			for i := 0; i < 200; i++ {
				m.DeleteProject("proj", 1)
				m.DeleteSession("proj", "sess", 1)
			}
		}(w)
	}
	// Readers: serve-gate and barrier snapshot concurrently.
	for r := 0; r < 4; r++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			for i := 0; i < 200; i++ {
				_ = m.Serve([]archive.Record{rec}, "capture")
				_ = m.Barriers()
			}
		}()
	}
	wg.Wait()
}
