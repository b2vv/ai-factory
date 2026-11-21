package workflow

import (
	"bytes"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"strings"

	"aifactory.local/storage/internal/control"
	"aifactory.local/storage/internal/registry"
)

const documentPrefix = "# Factory structured workflow v1\n\n<!-- sha256:"

func hashBytes(b []byte) string { h := sha256.Sum256(b); return hex.EncodeToString(h[:]) }

// Document is a dedicated generated Markdown file; human prose belongs in a
// separate file. The checksum guards the entire structured block against edits.
// Its revision is the SHA-256 of the complete file, pinned by the operator request.
func Document(tasks []Task) ([]byte, error) {
	b, e := canonicalTasks(tasks)
	if e != nil {
		return nil, e
	}
	return []byte(documentPrefix + hashBytes(b) + " -->\n```json\n" + string(b) + "\n```\n"), nil
}
func readDocument(path string) ([]byte, []Task, error) {
	f, e := os.Open(path)
	if e != nil {
		return nil, nil, e
	}
	defer f.Close()
	info, e := f.Stat()
	if e != nil {
		return nil, nil, e
	}
	if !info.Mode().IsRegular() {
		return nil, nil, fmt.Errorf("workflow: regular dedicated file required")
	}
	b, e := io.ReadAll(io.LimitReader(f, MaxSnapshotBytes+1025))
	if e != nil {
		return nil, nil, e
	}
	if len(b) > MaxSnapshotBytes+1024 {
		return nil, nil, fmt.Errorf("workflow: document too large")
	}
	text := string(b)
	if !strings.HasPrefix(text, documentPrefix) {
		return nil, nil, fmt.Errorf("workflow: refusing human/unrecognized document")
	}
	parts := strings.SplitN(strings.TrimPrefix(text, documentPrefix), " -->\n```json\n", 2)
	if len(parts) != 2 || !strings.HasSuffix(parts[1], "\n```\n") {
		return nil, nil, fmt.Errorf("workflow: invalid generated document")
	}
	body := []byte(strings.TrimSuffix(parts[1], "\n```\n"))
	if parts[0] != hashBytes(body) {
		return nil, nil, fmt.Errorf("workflow: generated region manually edited (hash mismatch)")
	}
	var tasks []Task
	dec := json.NewDecoder(bytes.NewReader(body))
	dec.DisallowUnknownFields()
	if e = dec.Decode(&tasks); e != nil {
		return nil, nil, e
	}
	canonical, e := Document(tasks)
	if e != nil {
		return nil, nil, e
	}
	if !bytes.Equal(canonical, b) {
		return nil, nil, fmt.Errorf("workflow: noncanonical document")
	}
	return b, tasks, nil
}

// Cutover verifies actual file/database bytes under the shared write fence. The
// caller must hold exclusive control ownership and freeze external edits to this
// dedicated file for the operation; a revision mismatch fails closed. It never
// changes human prose. Paths are operator-only, never supplied by an agent token.
func Cutover(d *control.Durable, store SnapshotStore, actor registry.Principal, project, path, revision string, to registry.WorkflowOwner) (control.WorkflowReceipt, error) {
	owner, epoch, ok := d.Registry().WorkflowAuthority(project)
	if !ok {
		return control.WorkflowReceipt{}, registry.ErrUnknownProj
	}
	if !filepath.IsAbs(path) || revision == "" {
		return control.WorkflowReceipt{}, fmt.Errorf("workflow: absolute dedicated path and source revision required")
	}
	return d.CutoverWorkflow(actor, project, owner, epoch, to, func() (string, string, error) {
		if !store.Available() {
			return "", "", ErrBlockedPGDown
		}
		before, tasks, e := readDocument(path)
		if e != nil {
			return "", "", e
		}
		if hashBytes(before) != revision {
			return "", "", fmt.Errorf("workflow: source revision changed")
		}
		if to == registry.OwnerPostgres {
			cost, e := ReservationBytes(project, tasks)
			if e != nil {
				return "", "", e
			}
			if e = d.ReserveExternalBytes(cost); e != nil {
				return "", "", e
			}
			if e = store.Replace(project, tasks); e != nil {
				return "", "", e
			}
			actual, e := store.Snapshot(project)
			if e != nil {
				return "", "", e
			}
			want, _ := canonicalTasks(tasks)
			got, e := canonicalTasks(actual)
			if e != nil {
				return "", "", e
			}
			if !bytes.Equal(want, got) {
				return "", "", fmt.Errorf("workflow: imported data verification failed")
			}
			after, _, e := readDocument(path)
			if e != nil {
				return "", "", e
			}
			if !bytes.Equal(before, after) {
				return "", "", fmt.Errorf("workflow: source changed during import")
			}
			return revision, hashBytes(got), nil
		}
		current, e := store.Snapshot(project)
		if e != nil {
			return "", "", e
		}
		output, e := Document(current)
		if e != nil {
			return "", "", e
		}
		if e = d.RegisterManagedPath(path, ".workflow-cutover-"); e != nil {
			return "", "", e
		}
		if e = d.ReserveExternalBytes(int64(len(output))); e != nil {
			return "", "", e
		}
		f, e := os.CreateTemp(filepath.Dir(path), ".workflow-cutover-*")
		if e != nil {
			return "", "", e
		}
		name := f.Name()
		defer os.Remove(name)
		if _, e = f.Write(output); e == nil {
			e = f.Sync()
		}
		closeErr := f.Close()
		if e == nil {
			e = closeErr
		}
		if e != nil {
			return "", "", e
		}
		check, _, e := readDocument(path)
		if e != nil {
			return "", "", e
		}
		if !bytes.Equal(check, before) {
			return "", "", fmt.Errorf("workflow: destination edited during export")
		}
		if e = os.Rename(name, path); e != nil {
			return "", "", e
		}
		dir, e := os.Open(filepath.Dir(path))
		if e != nil {
			return "", "", e
		}
		e = dir.Sync()
		dir.Close()
		if e != nil {
			return "", "", e
		}
		written, _, e := readDocument(path)
		if e != nil {
			return "", "", e
		}
		if !bytes.Equal(written, output) {
			return "", "", fmt.Errorf("workflow: export verification failed")
		}
		raw, _ := canonicalTasks(current)
		return revision, hashBytes(raw), nil
	})
}

// VerifiedDocument loads the exact dedicated source revision without modifying it.
func VerifiedDocument(path, revision string) ([]Task, error) {
	if !filepath.IsAbs(path) || revision == "" {
		return nil, fmt.Errorf("workflow: absolute source path and revision required")
	}
	raw, tasks, e := readDocument(path)
	if e != nil {
		return nil, e
	}
	if hashBytes(raw) != revision {
		return nil, fmt.Errorf("workflow: source revision mismatch")
	}
	return tasks, nil
}
