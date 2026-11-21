// Package backup provides bounded, integrity-checked logical snapshots. It does
// not back up or replace control authority. Restore requires the current control
// lineage, offline exclusive ownership, and empty destination project stores.
package backup

import (
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

const MaxBytes = 32 << 20

type Project struct {
	ID      string
	Owner   registry.WorkflowOwner
	Epoch   int64
	Archive []archive.Record
	Tasks   []workflow.Task
}
type Snapshot struct {
	Version  int
	Created  time.Time
	Projects []Project
}
type envelope struct {
	SHA256  string
	Payload json.RawMessage
}
type Result struct {
	Restored int
	Withheld int
	Projects int
}

func digest(b []byte) string { v := sha256.Sum256(b); return hex.EncodeToString(v[:]) }

// Create refuses oversized snapshots; it never silently truncates a backup.
// Larger datasets require a separately implemented streaming backup workflow.
func Create(d *control.Durable, actor registry.Principal, a archive.Store, p workflow.SnapshotStore, projects []string, out io.Writer) error {
	return d.WithStableAuthority(actor, func(reg *registry.Registry) error {
		snap := Snapshot{Version: 1, Created: time.Now().UTC()}
		seen := map[string]bool{}
		used := 0
		for _, id := range projects {
			if seen[id] {
				return fmt.Errorf("backup: duplicate project")
			}
			seen[id] = true
			owner, epoch, ok := reg.WorkflowAuthority(id)
			if !ok {
				return registry.ErrUnknownProj
			}
			item := Project{ID: id, Owner: owner, Epoch: epoch, Archive: []archive.Record{}}
			var after *archive.Position
			for {
				window, e := a.Scan(id, after)
				if e != nil {
					return e
				}
				for _, r := range window.Records {
					b, e := json.Marshal(r)
					if e != nil {
						return e
					}
					used += len(b)
					if used > MaxBytes {
						return fmt.Errorf("backup: snapshot size limit exceeded")
					}
					item.Archive = append(item.Archive, r)
				}
				if !window.More {
					break
				}
				if len(window.Records) == 0 {
					return fmt.Errorf("backup: nonprogressing archive cursor")
				}
				pos := archive.PositionOf(window.Records[len(window.Records)-1])
				after = &pos
			}
			var e error
			item.Tasks, e = p.Snapshot(id)
			if e != nil {
				return e
			}
			snap.Projects = append(snap.Projects, item)
		}
		payload, e := json.Marshal(snap)
		if e != nil {
			return e
		}
		if len(payload) > MaxBytes {
			return fmt.Errorf("backup: snapshot size limit exceeded")
		}
		return json.NewEncoder(out).Encode(envelope{SHA256: digest(payload), Payload: payload})
	})
}

// Restore validates the complete backup before touching either destination. It is
// not a cross-database transaction: errors return partial counts and require the
// operator to keep the destination offline. No stale control backup is accepted.
func Restore(d *control.Durable, actor registry.Principal, a archive.Store, p workflow.SnapshotStore, input io.Reader, now time.Time) (Result, error) {
	var result Result
	snap, e := ReadSnapshot(input, now)
	if e != nil {
		return result, e
	}
	e = d.WithStableAuthority(actor, func(reg *registry.Registry) error {
		seen := map[string]bool{}
		// Preflight all targets before the first write.
		for _, item := range snap.Projects {
			if seen[item.ID] {
				return fmt.Errorf("backup: duplicate project")
			}
			seen[item.ID] = true
			owner, epoch, ok := reg.WorkflowAuthority(item.ID)
			if !ok || owner != item.Owner || epoch != item.Epoch {
				return fmt.Errorf("backup: current workflow authority differs; explicit reconciliation required")
			}
			if _, e := workflow.Document(item.Tasks); e != nil {
				return e
			}
			ids := map[string]bool{}
			for _, r := range item.Archive {
				if r.Project != item.ID || ids[archive.IdentityKey(r)] {
					return fmt.Errorf("backup: mismatched or duplicate archive identity")
				}
				ids[archive.IdentityKey(r)] = true
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
		}
		var planned int64
		for _, item := range snap.Projects {
			cost, e := workflow.ReservationBytes(item.ID, item.Tasks)
			if e != nil {
				return e
			}
			planned += cost
			for _, rec := range d.Retention().Restore(item.Archive, "capture") {
				planned += archive.ReservationBytes(rec)
			}
		}
		if e := d.ReserveExternalBytes(planned); e != nil {
			return e
		}
		for _, item := range snap.Projects {
			if invalidator, ok := p.(interface{ InvalidateDerived(string) error }); ok {
				if e := invalidator.InvalidateDerived(item.ID); e != nil {
					return e
				}
			}
			allowed := d.Retention().Restore(item.Archive, "capture")
			result.Withheld += len(item.Archive) - len(allowed)
			for _, r := range allowed {
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
			result.Projects++
		}
		return nil
	})
	return result, e
}

func ReadSnapshot(input io.Reader, now time.Time) (Snapshot, error) {
	return readSnapshot(input, now, false)
}

func readSnapshot(input io.Reader, now time.Time, allowExpired bool) (Snapshot, error) {
	b, e := io.ReadAll(io.LimitReader(input, MaxBytes+1025))
	if e != nil {
		return Snapshot{}, e
	}
	if len(b) > MaxBytes+1024 {
		return Snapshot{}, fmt.Errorf("backup: size limit exceeded")
	}
	var env envelope
	if e = json.Unmarshal(b, &env); e != nil {
		return Snapshot{}, e
	}
	if digest(env.Payload) != env.SHA256 {
		return Snapshot{}, fmt.Errorf("backup: checksum mismatch")
	}
	var snap Snapshot
	dec := json.NewDecoder(bytes.NewReader(env.Payload))
	dec.DisallowUnknownFields()
	if e = dec.Decode(&snap); e != nil {
		return Snapshot{}, e
	}
	if snap.Version != 1 || snap.Created.IsZero() || snap.Created.After(now) || (!allowExpired && now.Sub(snap.Created) > 30*24*time.Hour) {
		return Snapshot{}, fmt.Errorf("backup: unsupported version or expired timestamp")
	}
	return snap, nil
}
