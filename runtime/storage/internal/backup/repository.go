package backup

import (
	"fmt"
	"io"
	"os"
	"path/filepath"
	"regexp"
	"sync"
	"syscall"

	"aifactory.local/storage/internal/config"
)

var backupName = regexp.MustCompile(`^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}\.backup$`)

// Repository is an explicitly chosen operator-owned backup directory. Its lock
// serializes all writers; all regular file bytes, including incomplete files, count
// against the aggregate budget. It never evicts an existing backup to admit another.
type Repository struct {
	mu               sync.Mutex
	dir              string
	budget, headroom int64
	lock             *os.File
}

func OpenRepository(dir string, budget, headroom int64) (*Repository, error) {
	if !filepath.IsAbs(dir) || budget <= 0 || headroom < 0 {
		return nil, fmt.Errorf("backup: absolute directory and positive budget required")
	}
	// Do not create or follow an unexpected alias to another operator's directory.
	resolved, e := filepath.EvalSymlinks(dir)
	if e != nil {
		return nil, e
	}
	if filepath.Clean(resolved) != filepath.Clean(dir) {
		return nil, fmt.Errorf("backup: symlink directory refused")
	}
	st, e := os.Stat(dir)
	if e != nil {
		return nil, e
	}
	if !st.IsDir() || st.Mode().Perm()&0077 != 0 {
		return nil, fmt.Errorf("backup: private directory required")
	}
	path := filepath.Join(dir, ".backup.lock")
	fd, e := syscall.Open(path, syscall.O_RDWR|syscall.O_CREAT|syscall.O_NOFOLLOW, 0600)
	if e != nil {
		return nil, e
	}
	f := os.NewFile(uintptr(fd), path)
	if e = syscall.Flock(fd, syscall.LOCK_EX|syscall.LOCK_NB); e != nil {
		f.Close()
		return nil, fmt.Errorf("backup: directory busy: %w", e)
	}
	return &Repository{dir: dir, budget: budget, headroom: headroom, lock: f}, nil
}
func (r *Repository) Close() error { return r.lock.Close() }
func (r *Repository) usage() (int64, error) {
	entries, e := os.ReadDir(r.dir)
	if e != nil {
		return 0, e
	}
	var used int64
	for _, entry := range entries {
		info, e := entry.Info()
		if e != nil {
			return 0, e
		}
		if !info.Mode().IsRegular() {
			return 0, fmt.Errorf("backup: nonregular directory entry refused")
		}
		if info.Size() > r.budget-used {
			return r.budget, fmt.Errorf("backup: existing files exceed budget")
		}
		used += info.Size()
	}
	return used, nil
}

type budgetWriter struct {
	file                *os.File
	remaining, headroom int64
}

func (w *budgetWriter) Write(p []byte) (int, error) {
	if int64(len(p)) > w.remaining {
		return 0, fmt.Errorf("backup: aggregate budget exceeded before write")
	}
	var stat syscall.Statfs_t
	if e := syscall.Fstatfs(int(w.file.Fd()), &stat); e != nil {
		return 0, e
	}
	free := uint64(stat.Bavail) * uint64(stat.Bsize)
	if uint64(w.headroom) > free || uint64(len(p)) > free-uint64(w.headroom) {
		return 0, fmt.Errorf("backup: free headroom exhausted")
	}
	n, e := w.file.Write(p)
	w.remaining -= int64(n)
	return n, e
}

// Save publishes with an exclusive hard-link operation, never replaces a file.
// Errors after publication can be ambiguous: the caller must inspect the named
// backup before retrying. Only this call's incomplete temporary file is removed.
func (r *Repository) Save(name string, produce func(io.Writer) error) error {
	r.mu.Lock()
	defer r.mu.Unlock()
	if !backupName.MatchString(name) {
		return fmt.Errorf("backup: invalid .backup name")
	}
	if _, e := os.Lstat(filepath.Join(r.dir, name)); !os.IsNotExist(e) {
		return fmt.Errorf("backup: destination exists or cannot be checked")
	}
	used, e := r.usage()
	if e != nil {
		return e
	}
	f, e := os.CreateTemp(r.dir, ".pending-backup-")
	if e != nil {
		return e
	}
	defer os.Remove(f.Name())
	defer f.Close()
	if e = produce(&budgetWriter{file: f, remaining: r.budget - used, headroom: r.headroom}); e != nil {
		return e
	}
	if e = f.Sync(); e != nil {
		return e
	}
	if e = f.Close(); e != nil {
		return e
	}
	if e = os.Link(f.Name(), filepath.Join(r.dir, name)); e != nil {
		return e
	}
	if e = os.Remove(f.Name()); e != nil {
		return e
	}
	d, e := os.Open(r.dir)
	if e != nil {
		return e
	}
	defer d.Close()
	return d.Sync()
}
func (r *Repository) Open(name string) (*os.File, error) {
	if !backupName.MatchString(name) {
		return nil, fmt.Errorf("backup: invalid .backup name")
	}
	path := filepath.Join(r.dir, name)
	fd, e := syscall.Open(path, syscall.O_RDONLY|syscall.O_NOFOLLOW, 0)
	if e != nil {
		return nil, e
	}
	f := os.NewFile(uintptr(fd), path)
	st, e := f.Stat()
	if e != nil {
		f.Close()
		return nil, e
	}
	if !st.Mode().IsRegular() || st.Mode().Perm()&0077 != 0 || st.Size() > MaxStreamBytes {
		f.Close()
		return nil, fmt.Errorf("backup: invalid or oversized snapshot")
	}
	return f, nil
}
func OpenDefaultRepository(dir string) (*Repository, error) {
	return OpenRepository(dir, config.DefaultBackupBudget, config.DefaultFreeHeadroom)
}
