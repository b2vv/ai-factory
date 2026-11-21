// Package meter measures the D4 capacity usage the Accountant admits against. It is a real
// measurement of the local state footprint and free space (plus an optional archive-DB
// contribution supplied by the caller). A measurement ERROR is returned and must be treated
// as fail-closed by the caller: a failure to measure must NEVER be read as unlimited
// capacity.
package meter

import (
	"os"
	"path/filepath"
	"syscall"

	"aifactory.local/storage/internal/config"
)

// dirSize sums the sizes of regular files under root. A missing root is 0 bytes (not an
// error); any other stat/walk error is returned.
func dirSize(root string) (int64, error) {
	var total int64
	err := filepath.WalkDir(root, func(p string, d os.DirEntry, err error) error {
		if err != nil {
			if os.IsNotExist(err) {
				return nil
			}
			return err
		}
		if d.IsDir() {
			return nil
		}
		info, err := d.Info()
		if err != nil {
			return err
		}
		if info.Mode().IsRegular() {
			total += info.Size()
		}
		return nil
	})
	if os.IsNotExist(err) {
		return 0, nil
	}
	return total, err
}

// Measure computes usage from the local filesystem: WALBytes is the ingestion WAL directory
// footprint, LiveBytes is the whole state-dir footprint plus extraLiveBytes (e.g. the
// archive DB storage size), and FreeBytes is the free space on the state volume. Any error
// is returned so the caller can fail closed.
func Measure(stateDir, walDir string, extraLiveBytes int64) (config.Usage, error) {
	walBytes, err := dirSize(walDir)
	if err != nil {
		return config.Usage{}, err
	}
	liveBytes, err := dirSize(stateDir)
	if err != nil {
		return config.Usage{}, err
	}
	var st syscall.Statfs_t
	if err := syscall.Statfs(stateDir, &st); err != nil {
		return config.Usage{}, err
	}
	free := int64(st.Bavail) * int64(st.Bsize)
	return config.Usage{WALBytes: walBytes, LiveBytes: liveBytes + extraLiveBytes, FreeBytes: free}, nil
}
