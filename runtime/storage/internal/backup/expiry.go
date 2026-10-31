package backup

import (
	"fmt"
	"os"
	"path/filepath"
	"time"

	"aifactory.local/storage/internal/config"
)

type ExpiryResult struct {
	Removed  []string
	Retained []string
}

// Expire is explicit operator maintenance under the repository's exclusive lock.
// It uses verified snapshot timestamps, never filenames or filesystem mtimes.
// Unknown files remain budget-accounted. Every eligible file is validated before
// deleting any; malformed snapshots fail closed. It never evicts a current backup
// just to admit another. Other same-OS-user writers must respect the directory lock.
func (r *Repository) Expire(now time.Time) (ExpiryResult, error) {
	r.mu.Lock()
	defer r.mu.Unlock()
	result := ExpiryResult{Removed: []string{}, Retained: []string{}}
	entries, e := os.ReadDir(r.dir)
	if e != nil {
		return result, e
	}
	type candidate struct {
		name string
		info os.FileInfo
	}
	var expired []candidate
	for _, entry := range entries {
		name := entry.Name()
		if !backupName.MatchString(name) {
			continue
		}
		f, e := r.Open(name)
		if e != nil {
			return result, e
		}
		info, e := f.Stat()
		if e != nil {
			f.Close()
			return result, e
		}
		created, e := inspectCreated(f, now)
		f.Close()
		if e != nil {
			return result, fmt.Errorf("backup: expiry validation failed for %s: %w", name, e)
		}
		if now.Sub(created) > time.Duration(config.DefaultBackupMaxAgeDays)*24*time.Hour {
			expired = append(expired, candidate{name, info})
		} else {
			result.Retained = append(result.Retained, name)
		}
	}
	// Recheck all selected names before the first unlink. Private-directory locking
	// is the ownership boundary, not a promise against a malicious same-user writer.
	for _, c := range expired {
		info, e := os.Lstat(filepath.Join(r.dir, c.name))
		if e != nil {
			return result, e
		}
		if !info.Mode().IsRegular() || !os.SameFile(c.info, info) {
			return result, fmt.Errorf("backup: expiry target changed")
		}
	}
	for _, c := range expired {
		if e = os.Remove(filepath.Join(r.dir, c.name)); e != nil {
			return result, e
		}
		result.Removed = append(result.Removed, c.name)
	}
	if len(result.Removed) > 0 {
		d, e := os.Open(r.dir)
		if e != nil {
			return result, e
		}
		defer d.Close()
		if e = d.Sync(); e != nil {
			return result, e
		}
	}
	return result, nil
}
