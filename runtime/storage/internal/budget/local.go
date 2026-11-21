package budget

import (
	"fmt"
	"io"
	"os"
	"path/filepath"
	"syscall"
)

// LocalSample streams the private state tree in small directory batches. Every
// regular managed file (including staging and failed writes) is billed; links and
// unknown file kinds refuse. The fixed accounting file has its own component.
func LocalSample(root string, limit int64) (Sample, error) {
	var total int64
	entries := 0
	var walk func(string, int) error
	walk = func(path string, depth int) error {
		if depth > 16 {
			return fmt.Errorf("budget: state nesting exceeds bounded inventory")
		}
		f, e := os.Open(path)
		if e != nil {
			return e
		}
		defer f.Close()
		for {
			batch, e := f.ReadDir(64)
			for _, entry := range batch {
				entries++
				if entries > 100000 {
					return fmt.Errorf("budget: excessive managed files")
				}
				child := filepath.Join(path, entry.Name())
				if depth == 0 && entry.Name() == "budget.bin" {
					continue
				}
				st, e := entry.Info()
				if e != nil {
					return e
				}
				if st.IsDir() {
					if e = walk(child, depth+1); e != nil {
						return e
					}
					continue
				}
				if !st.Mode().IsRegular() {
					return fmt.Errorf("budget: nonregular managed state")
				}
				if st.Size() < 0 || total > limit || st.Size() > limit-total {
					return ErrCapacity
				}
				total += st.Size()
			}
			if e == io.EOF {
				return nil
			}
			if e != nil {
				return e
			}
		}
	}
	if e := walk(root, 0); e != nil {
		return Sample{}, e
	}
	var stat syscall.Statfs_t
	if e := syscall.Statfs(root, &stat); e != nil {
		return Sample{}, e
	}
	free := uint64(stat.Bavail) * uint64(stat.Bsize)
	if free > uint64(^uint64(0)>>1) {
		return Sample{}, ErrBlocked
	}
	external, e := externalBytes(root, limit-total)
	if e != nil {
		return Sample{}, e
	}
	available, e := externalFree(root, int64(free))
	if e != nil {
		return Sample{}, e
	}
	return Sample{Components: map[string]int64{"local": total, "managed-external": external}, Free: available}, nil
}
