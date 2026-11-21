package backup

import (
	"bufio"
	"bytes"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"io"
	"time"

	"aifactory.local/storage/internal/archive"
	"aifactory.local/storage/internal/control"
	"aifactory.local/storage/internal/registry"
	"aifactory.local/storage/internal/workflow"
)

const streamMagic = "AIFACTORY-BACKUP-2\n"
const MaxStreamBytes int64 = 20 << 30
const maxFrameBytes = 16 << 20
const maxBackupProjects = 10000

type streamFrame struct {
	Kind    string
	Created time.Time       `json:",omitempty"`
	Project *Project        `json:",omitempty"`
	Record  *archive.Record `json:",omitempty"`
	SHA256  string          `json:",omitempty"`
	Count   uint64          `json:",omitempty"`
}

// walkStream bounds each decoded frame and the total file. The footer authenticates
// the complete preceding byte stream against accidental corruption/truncation; it
// is not a signature against a malicious operator. Rows are strictly keyset ordered.
func walkStream(input io.Reader, now time.Time, allowExpired bool, visit func(streamFrame) error) (time.Time, error) {
	limited := &io.LimitedReader{R: input, N: MaxStreamBytes + 1}
	scan := bufio.NewScanner(limited)
	scan.Buffer(make([]byte, 64<<10), maxFrameBytes)
	hash := sha256.New()
	var count uint64
	if !scan.Scan() || string(scan.Bytes())+"\n" != streamMagic {
		return time.Time{}, fmt.Errorf("backup: invalid stream magic")
	}
	hash.Write([]byte(streamMagic))
	created := time.Time{}
	project := ""
	seen := map[string]bool{}
	var last *archive.Position
	ended := false
	for scan.Scan() {
		if ended {
			return created, fmt.Errorf("backup: bytes after stream footer")
		}
		raw := scan.Bytes()
		var frame streamFrame
		dec := json.NewDecoder(bytes.NewReader(raw))
		dec.DisallowUnknownFields()
		if e := dec.Decode(&frame); e != nil {
			return created, e
		}
		var extra any
		if e := dec.Decode(&extra); e != io.EOF {
			return created, fmt.Errorf("backup: trailing frame data")
		}
		if frame.Kind == "end" {
			if created.IsZero() || frame.Project != nil || frame.Record != nil || frame.Count != count || frame.SHA256 != hex.EncodeToString(hash.Sum(nil)) {
				return created, fmt.Errorf("backup: stream checksum/count mismatch")
			}
			ended = true
			continue
		}
		hash.Write(raw)
		hash.Write([]byte{'\n'})
		count++
		switch frame.Kind {
		case "header":
			if count != 1 || frame.Project != nil || frame.Record != nil || frame.Created.IsZero() || frame.Created.After(now) || (!allowExpired && now.Sub(frame.Created) > 30*24*time.Hour) {
				return created, fmt.Errorf("backup: invalid or expired stream header")
			}
			created = frame.Created
		case "project":
			if created.IsZero() || frame.Project == nil || frame.Record != nil {
				return created, fmt.Errorf("backup: invalid project frame")
			}
			p := frame.Project
			if p.ID == "" || seen[p.ID] || len(seen) >= maxBackupProjects || p.Epoch < 1 || (p.Owner != registry.OwnerMarkdown && p.Owner != registry.OwnerPostgres) || len(p.Archive) != 0 {
				return created, fmt.Errorf("backup: duplicate/invalid project or project limit")
			}
			if _, e := workflow.Document(p.Tasks); e != nil {
				return created, e
			}
			seen[p.ID] = true
			project = p.ID
			last = nil
		case "record":
			if frame.Record == nil || frame.Project != nil || project == "" || frame.Record.Project != project {
				return created, fmt.Errorf("backup: invalid archive frame")
			}
			pos := archive.PositionOf(*frame.Record)
			if last != nil && !archive.Less(*last, pos) {
				return created, fmt.Errorf("backup: archive order is not strictly increasing")
			}
			last = &pos
		default:
			return created, fmt.Errorf("backup: unknown stream frame")
		}
		if visit != nil {
			if e := visit(frame); e != nil {
				return created, e
			}
		}
	}
	if e := scan.Err(); e != nil {
		return created, e
	}
	if limited.N <= 0 || !ended {
		return created, fmt.Errorf("backup: truncated or oversized stream")
	}
	return created, nil
}

// CreateStream keeps only one bounded archive window and one bounded workflow
// project in memory. The repository still enforces the aggregate disk budget.
func CreateStream(d *control.Durable, actor registry.Principal, a archive.Store, p workflow.SnapshotStore, projects []string, out io.Writer) error {
	if len(projects) > maxBackupProjects {
		return fmt.Errorf("backup: project limit exceeded")
	}
	return d.WithStableAuthority(actor, func(reg *registry.Registry) error {
		hash := sha256.New()
		writer := io.MultiWriter(out, hash)
		count := uint64(0)
		written := int64(len(streamMagic))
		if _, e := io.WriteString(writer, streamMagic); e != nil {
			return e
		}
		emit := func(frame streamFrame) error {
			raw, e := json.Marshal(frame)
			if e != nil {
				return e
			}
			raw = append(raw, '\n')
			if len(raw) >= maxFrameBytes || written+int64(len(raw))+512 > MaxStreamBytes {
				return fmt.Errorf("backup: frame or stream size limit")
			}
			if _, e = writer.Write(raw); e != nil {
				return e
			}
			written += int64(len(raw))
			count++
			return nil
		}
		if e := emit(streamFrame{Kind: "header", Created: time.Now().UTC()}); e != nil {
			return e
		}
		seen := map[string]bool{}
		for _, id := range projects {
			if seen[id] {
				return fmt.Errorf("backup: duplicate project")
			}
			seen[id] = true
			owner, epoch, ok := reg.WorkflowAuthority(id)
			if !ok {
				return registry.ErrUnknownProj
			}
			tasks, e := p.Snapshot(id)
			if e != nil {
				return e
			}
			if _, e = workflow.Document(tasks); e != nil {
				return e
			}
			if e = emit(streamFrame{Kind: "project", Project: &Project{ID: id, Owner: owner, Epoch: epoch, Tasks: tasks}}); e != nil {
				return e
			}
			var after *archive.Position
			for {
				window, e := a.Scan(id, after)
				if e != nil {
					return e
				}
				for _, r := range window.Records {
					pos := archive.PositionOf(r)
					if r.Project != id || (after != nil && !archive.Less(*after, pos)) {
						return fmt.Errorf("backup: invalid source cursor")
					}
					if e = emit(streamFrame{Kind: "record", Record: &r}); e != nil {
						return e
					}
					after = &pos
				}
				if !window.More {
					break
				}
				if len(window.Records) == 0 {
					return fmt.Errorf("backup: nonprogressing source")
				}
			}
		}
		return json.NewEncoder(out).Encode(streamFrame{Kind: "end", SHA256: hex.EncodeToString(hash.Sum(nil)), Count: count})
	})
}

func isStream(reader *bufio.Reader) bool {
	b, e := reader.Peek(len(streamMagic))
	return e == nil && string(b) == streamMagic
}

// RestoreFile verifies all bytes, structure, current authority and empty targets
// BEFORE any write, then reads the seekable private file again under the same
// control fence. DB errors/conflicting archive identities still yield an explicit
// partial offline result, not cross-database atomic success. Operator must freeze
// external writers, including modifications to the input file, for both passes.
func RestoreFile(d *control.Durable, actor registry.Principal, a archive.Store, p workflow.SnapshotStore, input io.ReadSeeker, now time.Time) (Result, error) {
	var result Result
	if _, e := input.Seek(0, io.SeekStart); e != nil {
		return result, e
	}
	if !isStream(bufio.NewReader(input)) {
		if _, e := input.Seek(0, io.SeekStart); e != nil {
			return result, e
		}
		return Restore(d, actor, a, p, input, now)
	}
	e := d.WithStableAuthority(actor, func(reg *registry.Registry) error {
		if _, e := input.Seek(0, io.SeekStart); e != nil {
			return e
		}
		var planned int64
		_, e := walkStream(input, now, false, func(f streamFrame) error {
			if f.Kind == "record" && len(d.Retention().Restore([]archive.Record{*f.Record}, "capture")) != 0 {
				planned += archive.ReservationBytes(*f.Record)
			}
			if f.Kind == "project" {
				cost, e := workflow.ReservationBytes(f.Project.ID, f.Project.Tasks)
				if e != nil {
					return e
				}
				planned += cost
			}
			if f.Kind != "project" {
				return nil
			}
			item := f.Project
			owner, epoch, ok := reg.WorkflowAuthority(item.ID)
			if !ok || owner != item.Owner || epoch != item.Epoch {
				return fmt.Errorf("backup: current workflow authority differs")
			}
			window, e := a.Scan(item.ID, nil)
			if e != nil {
				return e
			}
			if len(window.Records) > 0 || window.More {
				return fmt.Errorf("backup: archive destination must be empty")
			}
			tasks, e := p.Snapshot(item.ID)
			if e != nil {
				return e
			}
			if len(tasks) > 0 {
				return fmt.Errorf("backup: workflow destination must be empty")
			}
			return nil
		})
		if e != nil {
			return e
		}
		if _, e = input.Seek(0, io.SeekStart); e != nil {
			return e
		}
		if e := d.ReserveExternalBytes(planned); e != nil {
			return e
		}
		activeProject := false
		_, e = walkStream(input, now, false, func(f streamFrame) error {
			switch f.Kind {
			case "project":
				if activeProject {
					result.Projects++
				}
				activeProject = false
				item := f.Project
				if invalidator, ok := p.(interface{ InvalidateDerived(string) error }); ok {
					if e := invalidator.InvalidateDerived(item.ID); e != nil {
						return e
					}
				}
				if e := p.Replace(item.ID, item.Tasks); e != nil {
					return e
				}
				actual, e := p.Snapshot(item.ID)
				if e != nil {
					return e
				}
				want, e := workflow.Document(item.Tasks)
				if e != nil {
					return e
				}
				got, e := workflow.Document(actual)
				if e != nil {
					return e
				}
				if !bytes.Equal(want, got) {
					return fmt.Errorf("backup: workflow verification failed")
				}
				activeProject = true
			case "record":
				r := *f.Record
				if len(d.Retention().Restore([]archive.Record{r}, "capture")) == 0 {
					result.Withheld++
					return nil
				}
				if e := a.Put(r); e != nil {
					return e
				}
				actual, found, e := a.Lookup(r)
				if e != nil {
					return e
				}
				if !found || actual != r {
					return fmt.Errorf("backup: archive verification failed")
				}
				result.Restored++
			}
			return nil
		})
		if e == nil && activeProject {
			result.Projects++
		}
		return e
	})
	return result, e
}

// ReadWorkflowSnapshot verifies either format but retains only bounded workflow
// metadata for B5. Large archive payloads need not be materialized for PG rollback.
func ReadWorkflowSnapshot(input io.Reader, now time.Time) (Snapshot, error) {
	reader := bufio.NewReader(input)
	if !isStream(reader) {
		return ReadSnapshot(reader, now)
	}
	snap := Snapshot{Version: 2}
	used := 0
	created, e := walkStream(reader, now, false, func(f streamFrame) error {
		if f.Kind == "project" {
			b, e := json.Marshal(f.Project)
			if e != nil {
				return e
			}
			used += len(b)
			if used > MaxBytes {
				return fmt.Errorf("backup: workflow metadata limit exceeded")
			}
			snap.Projects = append(snap.Projects, *f.Project)
		}
		return nil
	})
	snap.Created = created
	return snap, e
}

func inspectCreated(input io.Reader, now time.Time) (time.Time, error) {
	reader := bufio.NewReader(input)
	if isStream(reader) {
		return walkStream(reader, now, true, nil)
	}
	snap, e := readSnapshot(reader, now, true)
	return snap.Created, e
}
