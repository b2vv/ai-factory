// Package documents adapts explicitly enrolled Markdown sources. A dedicated
// checksummed Markdown ledger owns stable IDs, revisions and deletion tombstones;
// PostgreSQL is only a rebuildable projection. Human document bytes are never
// rewritten by this adapter. There is no filesystem crawler or implicit capture.
package documents

import (
	"bytes"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"syscall"
)

const MaxBytes = 8 << 20
const MaxDocuments = 10000
const prefix = "# Factory document ledger v1\n\n<!-- sha256:"

type Entry struct {
	ID       string
	Path     string
	Revision string
	Version  int64
	Deleted  bool
}

func Digest(b []byte) string { h := sha256.Sum256(b); return hex.EncodeToString(h[:]) }
func pathOK(s string) bool {
	return s != "" && !filepath.IsAbs(s) && filepath.Clean(s) == s && s != ".." && !strings.HasPrefix(s, ".."+string(filepath.Separator))
}
func Encode(entries []Entry) ([]byte, error) {
	if len(entries) > MaxDocuments {
		return nil, fmt.Errorf("documents: entry limit")
	}
	rows := append([]Entry{}, entries...)
	sort.Slice(rows, func(i, j int) bool { return rows[i].ID < rows[j].ID })
	paths := map[string]bool{}
	for n, r := range rows {
		if r.ID == "" || len(r.ID) > 1024 || (!pathOK(r.Path) || len(r.Path) > 4096) || r.Version < 1 || len(r.Revision) != 64 || (n > 0 && rows[n-1].ID == r.ID) {
			return nil, fmt.Errorf("documents: invalid stable entry")
		}
		if _, e := hex.DecodeString(r.Revision); e != nil {
			return nil, e
		}
		if !r.Deleted {
			if paths[r.Path] {
				return nil, fmt.Errorf("documents: duplicate active path")
			}
			paths[r.Path] = true
		}
	}
	b, e := json.Marshal(rows)
	if e != nil {
		return nil, e
	}
	if len(b) > MaxBytes {
		return nil, fmt.Errorf("documents: ledger limit")
	}
	return []byte(prefix + Digest(b) + " -->\n```json\n" + string(b) + "\n```\n"), nil
}
func readRegular(path string, max int64) ([]byte, error) {
	st, e := os.Lstat(path)
	if e != nil {
		return nil, e
	}
	if !st.Mode().IsRegular() {
		return nil, fmt.Errorf("documents: regular file required")
	}
	f, e := os.Open(path)
	if e != nil {
		return nil, e
	}
	defer f.Close()
	opened, e := f.Stat()
	if e != nil {
		return nil, e
	}
	if !os.SameFile(st, opened) {
		return nil, fmt.Errorf("documents: source changed while opening")
	}
	b, e := io.ReadAll(io.LimitReader(f, max+1))
	if e != nil {
		return nil, e
	}
	if int64(len(b)) > max {
		return nil, fmt.Errorf("documents: source bound exceeded")
	}
	return b, nil
}
func Read(path string) ([]Entry, string, error) {
	b, e := readRegular(path, MaxBytes+1024)
	if e != nil {
		return nil, "", e
	}
	if !bytes.HasPrefix(b, []byte(prefix)) {
		return nil, "", fmt.Errorf("documents: dedicated ledger required")
	}
	parts := strings.SplitN(strings.TrimPrefix(string(b), prefix), " -->\n```json\n", 2)
	if len(parts) != 2 || !strings.HasSuffix(parts[1], "\n```\n") {
		return nil, "", fmt.Errorf("documents: invalid ledger")
	}
	raw := []byte(strings.TrimSuffix(parts[1], "\n```\n"))
	if Digest(raw) != parts[0] {
		return nil, "", fmt.Errorf("documents: edited generated ledger")
	}
	var rows []Entry
	dec := json.NewDecoder(bytes.NewReader(raw))
	dec.DisallowUnknownFields()
	if e = dec.Decode(&rows); e != nil {
		return nil, "", e
	}
	canonical, e := Encode(rows)
	if e != nil {
		return nil, "", e
	}
	if !bytes.Equal(canonical, b) {
		return nil, "", fmt.Errorf("documents: noncanonical ledger")
	}
	return rows, Digest(b), nil
}
func sourcePath(root, relative string) (string, error) {
	if !filepath.IsAbs(root) || !pathOK(relative) {
		return "", fmt.Errorf("documents: absolute root and confined relative source required")
	}
	canonical, e := filepath.EvalSymlinks(root)
	if e != nil {
		return "", e
	}
	if canonical != filepath.Clean(root) {
		return "", fmt.Errorf("documents: canonical source root required")
	}
	path := filepath.Join(root, relative)
	// Reject intermediate symlinks even when the final source was deleted.
	part := root
	for _, name := range strings.Split(relative, string(filepath.Separator)) {
		part = filepath.Join(part, name)
		st, e := os.Lstat(part)
		if os.IsNotExist(e) {
			break
		}
		if e != nil {
			return "", e
		}
		if st.Mode()&os.ModeSymlink != 0 {
			return "", fmt.Errorf("documents: symlink source refused")
		}
	}
	return path, nil
}

// VerifySource validates the stable identity marker and complete original bytes.
// The marker is a single leading HTML comment containing a JSON string, so plain
// Markdown remains fully readable without this service.
func VerifySource(root string, entry Entry) error {
	path, e := sourcePath(root, entry.Path)
	if e != nil {
		return e
	}
	if entry.Deleted {
		return nil
	}
	b, e := readRegular(path, MaxBytes)
	if e != nil {
		return e
	}
	identity, _ := json.Marshal(entry.ID)
	marker := "<!-- factory-document-id: " + string(identity) + " -->\n"
	if !bytes.HasPrefix(b, []byte(marker)) || Digest(b) != entry.Revision {
		return fmt.Errorf("documents: source identity/revision changed")
	}
	return nil
}

// Update is an explicit operator action under an exclusive ledger lock and a
// caller-held current control fence. expected is the complete prior ledger hash
// (empty only for initial creation). Rename preserves ID and increments version;
// deletion retains the prior source revision in a tombstone. Human files stay intact.
func Update(root, ledger, id, path, expected string, deleted bool) (string, error) {
	return UpdateBudgeted(root, ledger, id, path, expected, deleted, nil)
}

// UpdateBudgeted reserves the complete replacement temporary file before writing.
// The operator supplies the shared authority-fenced reservation callback.
func UpdateBudgeted(root, ledger, id, path, expected string, deleted bool, reserve func(int64) error) (string, error) {
	target, e := sourcePath(root, ledger)
	if e != nil {
		return "", e
	}
	if id == "" || path == ledger {
		return "", fmt.Errorf("documents: invalid document ID/path")
	}
	lock, e := os.OpenFile(target+".lock", os.O_CREATE|os.O_RDWR|syscall.O_NOFOLLOW, 0600)
	if e != nil {
		return "", e
	}
	defer lock.Close()
	if e = syscall.Flock(int(lock.Fd()), syscall.LOCK_EX); e != nil {
		return "", e
	}
	defer syscall.Flock(int(lock.Fd()), syscall.LOCK_UN)
	rows, revision, e := Read(target)
	if os.IsNotExist(e) {
		rows = []Entry{}
		revision = ""
	} else if e != nil {
		return "", e
	}
	if revision != expected {
		return "", fmt.Errorf("documents: ledger revision conflict")
	}
	at := -1
	for n, row := range rows {
		if row.ID == id {
			at = n
		}
	}
	if at >= 0 && rows[at].Deleted {
		return "", fmt.Errorf("documents: tombstoned ID cannot be reused; enroll a new identity")
	}
	next := Entry{ID: id, Path: path, Version: 1, Deleted: deleted}
	if at >= 0 {
		next.Version = rows[at].Version + 1
		if next.Version <= rows[at].Version {
			return "", fmt.Errorf("documents: version exhausted")
		}
	}
	if deleted {
		if at < 0 || rows[at].Deleted || path != rows[at].Path {
			return "", fmt.Errorf("documents: active source required for tombstone")
		}
		source, e := sourcePath(root, path)
		if e != nil {
			return "", e
		}
		if _, e = os.Lstat(source); !os.IsNotExist(e) {
			return "", fmt.Errorf("documents: remove source before tombstoning")
		}
		next.Revision = rows[at].Revision
	} else {
		source, e := sourcePath(root, path)
		if e != nil {
			return "", e
		}
		raw, e := readRegular(source, MaxBytes)
		if e != nil {
			return "", e
		}
		next.Revision = Digest(raw)
		if at >= 0 && rows[at].Path != path && !rows[at].Deleted {
			old, e := sourcePath(root, rows[at].Path)
			if e != nil {
				return "", e
			}
			if _, e = os.Lstat(old); !os.IsNotExist(e) {
				return "", fmt.Errorf("documents: rename requires old path absent")
			}
		}
	}
	if e = VerifySource(root, next); e != nil {
		return "", e
	}
	if at >= 0 {
		rows[at] = next
	} else {
		rows = append(rows, next)
	}
	out, e := Encode(rows)
	if e != nil {
		return "", e
	}
	if reserve != nil {
		if e = reserve(int64(len(out))); e != nil {
			return "", e
		}
	}
	f, e := os.CreateTemp(filepath.Dir(target), ".document-ledger-*")
	if e != nil {
		return "", e
	}
	temp := f.Name()
	defer os.Remove(temp)
	if _, e = f.Write(out); e == nil {
		e = f.Sync()
	}
	closeErr := f.Close()
	if e == nil {
		e = closeErr
	}
	if e != nil {
		return "", e
	}
	if e = VerifySource(root, next); e != nil {
		return "", e
	}
	_, current, readErr := Read(target)
	if os.IsNotExist(readErr) {
		current = ""
	} else if readErr != nil {
		return "", readErr
	}
	if current != expected {
		return "", fmt.Errorf("documents: ledger changed before publication")
	}
	if e = os.Rename(temp, target); e != nil {
		return "", e
	}
	dir, e := os.Open(filepath.Dir(target))
	if e != nil {
		return "", e
	}
	defer dir.Close()
	if e = dir.Sync(); e != nil {
		return "", e
	}
	return Digest(out), nil
}

func LedgerPath(root, relative string) (string, error) { return sourcePath(root, relative) }
