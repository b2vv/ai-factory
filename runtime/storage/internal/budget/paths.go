package budget

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"strings"
	"syscall"
)

type managedPath struct {
	Version             int
	Path, StagingPrefix string
}

const pathCatalog = "budget-paths"

// RegisterPath admits a durable reference to an explicitly selected generated
// file, not a crawler. Existing source files and surviving staging copies become
// part of every later offline/server inventory before a replacement is allowed.
func RegisterPath(root, target, prefix string, l *Ledger) error {
	if !filepath.IsAbs(target) || filepath.Clean(target) != target || len(target) > 4096 || strings.ContainsAny(prefix, "/\\") || prefix == "" {
		return ErrBlocked
	}
	rel, e := filepath.Rel(root, target)
	if e != nil {
		return e
	}
	if rel != ".." && !strings.HasPrefix(rel, ".."+string(os.PathSeparator)) {
		return nil
	}
	descriptor := managedPath{Version: Version, Path: target, StagingPrefix: prefix}
	raw, e := json.Marshal(descriptor)
	if e != nil {
		return e
	}
	h := sha256.Sum256([]byte(target))
	dir := filepath.Join(root, pathCatalog)
	path := filepath.Join(dir, hex.EncodeToString(h[:])+".json")
	if old, e := os.ReadFile(path); e == nil {
		if string(old) != string(raw) {
			return ErrBlocked
		}
		return nil
	} else if !os.IsNotExist(e) {
		return e
	}
	existing, e := pathBytes(descriptor, l.Snapshot().Policy.LiveCap)
	if e != nil {
		return e
	}
	payloadHash := sha256.Sum256(raw)
	if e = l.Reserve(Evidence{Kind: "path-registration", KeyHash: hex.EncodeToString(h[:]), PayloadHash: hex.EncodeToString(payloadHash[:])}, int64(len(raw))+existing); e != nil {
		return e
	}
	if e = os.MkdirAll(dir, 0700); e != nil {
		return e
	}
	f, e := os.OpenFile(path, os.O_WRONLY|os.O_CREATE|os.O_EXCL, 0600)
	if e != nil {
		return e
	}
	n, e := f.Write(raw)
	if e == nil && n != len(raw) {
		e = fmt.Errorf("budget: partial path descriptor")
	}
	if e == nil {
		e = f.Sync()
	}
	e = errors.Join(e, f.Close())
	if e != nil {
		return e
	}
	if e = syncDir(dir); e != nil {
		return e
	}
	if e = syncDir(root); e != nil {
		return e
	}
	return l.Finish()
}
func pathBytes(ref managedPath, limit int64) (int64, error) {
	if ref.Version != Version || !filepath.IsAbs(ref.Path) || filepath.Clean(ref.Path) != ref.Path || len(ref.Path) > 4096 || ref.StagingPrefix == "" || strings.ContainsAny(ref.StagingPrefix, "/\\") {
		return 0, ErrBlocked
	}
	var total int64
	add := func(path string) error {
		st, e := os.Lstat(path)
		if os.IsNotExist(e) {
			return nil
		}
		if e != nil {
			return e
		}
		if !st.Mode().IsRegular() {
			return ErrBlocked
		}
		if total > limit || st.Size() > limit-total {
			return ErrCapacity
		}
		total += st.Size()
		return nil
	}
	if e := add(ref.Path); e != nil {
		return 0, e
	}
	f, e := os.Open(filepath.Dir(ref.Path))
	if e != nil {
		return 0, e
	}
	defer f.Close()
	// Only the named writer's staging prefix in the selected parent is inspected.
	entries, e := f.ReadDir(10001)
	if e != nil && e != io.EOF {
		return 0, e
	}
	if len(entries) > 10000 {
		return 0, ErrBlocked
	}
	for _, entry := range entries {
		if strings.HasPrefix(entry.Name(), ref.StagingPrefix) {
			if e = add(filepath.Join(filepath.Dir(ref.Path), entry.Name())); e != nil {
				return 0, e
			}
		}
	}
	return total, nil
}
func externalBytes(root string, limit int64) (int64, error) {
	dir := filepath.Join(root, pathCatalog)
	f, e := os.Open(dir)
	if os.IsNotExist(e) {
		return 0, nil
	}
	if e != nil {
		return 0, e
	}
	defer f.Close()
	entries, e := f.ReadDir(10001)
	if os.IsNotExist(e) {
		return 0, nil
	}
	if e != nil && e != io.EOF {
		return 0, e
	}
	if len(entries) > 10000 {
		return 0, ErrBlocked
	}
	var total int64
	parents := map[string]string{}
	for _, entry := range entries {
		st, e := entry.Info()
		if e != nil {
			return 0, e
		}
		if !st.Mode().IsRegular() || st.Size() > 8192 {
			return 0, ErrBlocked
		}
		raw, e := os.ReadFile(filepath.Join(dir, entry.Name()))
		if e != nil {
			return 0, e
		}
		var ref managedPath
		if e = json.Unmarshal(raw, &ref); e != nil {
			return 0, e
		}
		h := sha256.Sum256([]byte(ref.Path))
		if entry.Name() != hex.EncodeToString(h[:])+".json" {
			return 0, ErrBlocked
		}
		// Avoid billing shared staging prefixes twice; the target itself remains unique.
		key := filepath.Dir(ref.Path) + "\x00" + ref.StagingPrefix
		original := ref.StagingPrefix
		if parents[key] != "" {
			ref.StagingPrefix = ".budget-no-staging-" + entry.Name()
		}
		parents[key] = original
		n, e := pathBytes(ref, limit-total)
		if e != nil {
			return 0, e
		}
		total += n
	}
	return total, nil
}

func RecoverPaths(root string, l *Ledger) error {
	pending := l.Snapshot().Pending
	if len(pending) == 0 {
		return nil
	}
	for _, p := range pending {
		if p.Evidence.Kind != "path-registration" {
			return nil
		}
	}
	return l.Recover(func(p Intent) (bool, error) {
		if len(p.Evidence.KeyHash) != 64 {
			return false, ErrBlocked
		}
		if _, e := hex.DecodeString(p.Evidence.KeyHash); e != nil {
			return false, ErrBlocked
		}
		path := filepath.Join(root, pathCatalog, p.Evidence.KeyHash+".json")
		st, e := os.Lstat(path)
		if os.IsNotExist(e) {
			return false, nil
		}
		if e != nil {
			return false, e
		}
		if !st.Mode().IsRegular() || st.Size() > 8192 {
			return false, ErrBlocked
		}
		raw, e := os.ReadFile(path)
		if e != nil {
			return false, e
		}
		sum := sha256.Sum256(raw)
		return hex.EncodeToString(sum[:]) == p.Evidence.PayloadHash, nil
	})
}

// Physical headroom is the minimum across the state and explicitly managed
// generated-file volumes; a different mount cannot hide its free-space shortage.
func externalFree(root string, free int64) (int64, error) {
	f, e := os.Open(filepath.Join(root, pathCatalog))
	if os.IsNotExist(e) {
		return free, nil
	}
	if e != nil {
		return 0, e
	}
	defer f.Close()
	entries, e := f.ReadDir(10001)
	if e != nil && e != io.EOF {
		return 0, e
	}
	if len(entries) > 10000 {
		return 0, ErrBlocked
	}
	for _, entry := range entries {
		st, e := entry.Info()
		if e != nil {
			return 0, e
		}
		if !st.Mode().IsRegular() || st.Size() > 8192 {
			return 0, ErrBlocked
		}
		raw, e := os.ReadFile(filepath.Join(root, pathCatalog, entry.Name()))
		if e != nil {
			return 0, e
		}
		var ref managedPath
		if e = json.Unmarshal(raw, &ref); e != nil {
			return 0, e
		}
		var stat syscall.Statfs_t
		if e = syscall.Statfs(filepath.Dir(ref.Path), &stat); e != nil {
			return 0, e
		}
		available := uint64(stat.Bavail) * uint64(stat.Bsize)
		if available > uint64(^uint64(0)>>1) {
			return 0, ErrBlocked
		}
		if int64(available) < free {
			free = int64(available)
		}
	}
	return free, nil
}
