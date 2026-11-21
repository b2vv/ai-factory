package backup

import (
	"io"
	"os"
	"path/filepath"
	"sync"
	"sync/atomic"
	"testing"
)

func TestRepositoryBudgetConcurrentFailureAndRecovery(t *testing.T) {
	dir := filepath.Join(t.TempDir(), "backups")
	if e := os.Mkdir(dir, 0700); e != nil {
		t.Fatal(e)
	}
	r, e := OpenRepository(dir, 10, 0)
	if e != nil {
		t.Fatal(e)
	}
	defer r.Close()
	if _, e = OpenRepository(dir, 10, 0); e == nil {
		t.Fatal("concurrent owner allowed")
	}
	var won atomic.Int32
	var wg sync.WaitGroup
	for _, name := range []string{"a.backup", "b.backup"} {
		wg.Add(1)
		go func(name string) {
			defer wg.Done()
			if r.Save(name, func(w io.Writer) error { _, e := io.WriteString(w, "123456"); return e }) == nil {
				won.Add(1)
			}
		}(name)
	}
	wg.Wait()
	if won.Load() != 1 {
		t.Fatal("budget overspent", won.Load())
	}
	used, e := r.usage()
	if e != nil || used != 6 {
		t.Fatal(used, e)
	}
	if e = r.Save("partial.backup", func(w io.Writer) error {
		if _, e := io.WriteString(w, "1234"); e != nil {
			return e
		}
		_, e := io.WriteString(w, "5")
		return e
	}); e == nil {
		t.Fatal("partial write exceeded budget")
	}
	used, e = r.usage()
	if e != nil || used != 6 {
		t.Fatal("failed reservation not reclaimed", used, e)
	}
	if e = r.Save("remaining.backup", func(w io.Writer) error { _, e := io.WriteString(w, "1234"); return e }); e != nil {
		t.Fatal(e)
	}
	if e = r.Save("remaining.backup", func(w io.Writer) error { t.Fatal("overwriting producer ran"); return nil }); e == nil {
		t.Fatal("overwrite allowed")
	}
}
func TestRepositoryCountsForeignAndIncompleteFiles(t *testing.T) {
	dir := filepath.Join(t.TempDir(), "backups")
	if e := os.Mkdir(dir, 0700); e != nil {
		t.Fatal(e)
	}
	if e := os.WriteFile(filepath.Join(dir, ".pending-old"), []byte("12345"), 0600); e != nil {
		t.Fatal(e)
	}
	r, e := OpenRepository(dir, 5, 0)
	if e != nil {
		t.Fatal(e)
	}
	defer r.Close()
	if e = r.Save("new.backup", func(w io.Writer) error { _, e := io.WriteString(w, "1"); return e }); e == nil {
		t.Fatal("ignored incomplete bytes")
	}
	if e = os.Symlink(".pending-old", filepath.Join(dir, "alias.backup")); e != nil {
		t.Fatal(e)
	}
	if _, e = r.Open("alias.backup"); e == nil {
		t.Fatal("followed symlink")
	}
	if e = r.Save("other.backup", func(w io.Writer) error { return nil }); e == nil {
		t.Fatal("ignored nonregular entry")
	}
}
