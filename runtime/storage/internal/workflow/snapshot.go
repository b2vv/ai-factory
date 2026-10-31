package workflow

import (
	"aifactory.local/storage/internal/logical"
	"context"
	"encoding/json"
	"fmt"
	"sort"
)

const MaxSnapshotBytes = 8 << 20
const MaxSnapshotTasks = 10000

type SnapshotStore interface {
	Store
	Snapshot(project string) ([]Task, error)
	Replace(project string, tasks []Task) error
}

func canonicalTasks(tasks []Task) ([]byte, error) {
	if len(tasks) > MaxSnapshotTasks {
		return nil, fmt.Errorf("workflow: snapshot task limit exceeded")
	}
	rows := append([]Task{}, tasks...)
	sort.Slice(rows, func(i, j int) bool { return rows[i].ID < rows[j].ID })
	for i, t := range rows {
		if t.ID == "" || t.Version < 1 || (i > 0 && rows[i-1].ID == t.ID) {
			return nil, fmt.Errorf("workflow: invalid or duplicate stable task ID/version")
		}
	}
	b, e := json.Marshal(rows)
	if e != nil {
		return nil, e
	}
	if len(b) > MaxSnapshotBytes {
		return nil, fmt.Errorf("workflow: snapshot byte limit exceeded")
	}
	return b, nil
}

func (s *PGStore) Snapshot(project string) ([]Task, error) {
	ctx, cancel := context.WithTimeout(context.Background(), s.opTimeout)
	defer cancel()
	rows, e := s.pool.Query(ctx, `SELECT id,version,fields FROM workflow_tasks WHERE project=$1 ORDER BY id LIMIT $2`, project, MaxSnapshotTasks+1)
	if e != nil {
		return nil, e
	}
	defer rows.Close()
	tasks := []Task{}
	bytes := 0
	for rows.Next() {
		var t Task
		var raw []byte
		if e = rows.Scan(&t.ID, &t.Version, &raw); e != nil {
			return nil, e
		}
		bytes += len(raw) + len(t.ID) + 32
		if bytes > MaxSnapshotBytes || len(tasks) >= MaxSnapshotTasks {
			return nil, fmt.Errorf("workflow: snapshot limit exceeded")
		}
		if e = json.Unmarshal(raw, &t.Fields); e != nil {
			return nil, e
		}
		tasks = append(tasks, t)
	}
	return tasks, rows.Err()
}

// Replace is used only under the control registry's cutover fence while Markdown
// still owns the project. The entire validated import commits in one transaction.
func (s *PGStore) Replace(project string, tasks []Task) error {
	if _, e := canonicalTasks(tasks); e != nil {
		return e
	}
	ctx, cancel := context.WithTimeout(context.Background(), s.opTimeout)
	defer cancel()
	tx, e := s.pool.Begin(ctx)
	if e != nil {
		return e
	}
	defer tx.Rollback(ctx)
	if _, e = tx.Exec(ctx, `DELETE FROM workflow_tasks WHERE project=$1`, project); e != nil {
		return e
	}
	for _, t := range tasks {
		b, e := json.Marshal(t.Fields)
		if e != nil {
			return e
		}
		if _, e = tx.Exec(ctx, `INSERT INTO workflow_tasks(project,id,version,fields) VALUES($1,$2,$3,$4)`, project, t.ID, t.Version, b); e != nil {
			return e
		}
	}
	return tx.Commit(ctx)
}

// ReservationBytes includes every task representation and primary-key tuple.
// It is a known serialized minimum, not PostgreSQL page/index allocation proof.
func ReservationBytes(project string, tasks []Task) (int64, error) {
	if _, e := canonicalTasks(tasks); e != nil {
		return 0, e
	}
	var total int64
	for _, task := range tasks {
		total += logical.Workflow(project, task.ID, task.Version, task.Fields)
	}
	return total, nil
}
