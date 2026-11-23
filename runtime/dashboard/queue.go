package main

import (
	"errors"
	"io"
	"time"
)

// A project's open tasks, published separately from the status record: the list is not bound to a revision,
// so it stays shown while HEAD moves and carries its own publish time.
const queueSchema = "factory-dashboard/queue/1"
const maxQueue = 32 << 10
const maxQueueItems = 64
const queueTTL = 7 * 24 * time.Hour

var queueStates = map[string]bool{"In progress": true, "Ready": true, "Proposed": true, "Paused": true, "Blocked": true}

var queueField = map[string]bool{
	"schema": true, "project": true, "updatedAt": true, "items": true, "omitted": true,
	"id": true, "title": true, "state": true, "summary": true, "blockedBy": true, "recommended": true,
}

type queueItem struct {
	ID          string `json:"id"`
	Title       string `json:"title"`
	State       string `json:"state"`
	Summary     string `json:"summary"`
	BlockedBy   string `json:"blockedBy,omitempty"`
	Recommended bool   `json:"recommended,omitempty"`
}
type queueRecord struct {
	Schema    string      `json:"schema"`
	Project   string      `json:"project"`
	UpdatedAt time.Time   `json:"updatedAt"`
	Items     []queueItem `json:"items"`
	Omitted   int         `json:"omitted"`
}
type queueDisplay struct {
	UpdatedAt time.Time   `json:"updatedAt"`
	Stale     bool        `json:"stale"`
	Items     []queueItem `json:"items"`
	Omitted   int         `json:"omitted"`
}

func decodeQueue(raw []byte) (queueRecord, error) {
	return decodeBounded[queueRecord](raw, maxQueue, queueField)
}

func (q queueRecord) validate(id string, now time.Time) error {
	if q.Schema != queueSchema || q.Project != id || projects.name(id) == "" {
		return errors.New("invalid queue schema or project")
	}
	if q.UpdatedAt.IsZero() || q.UpdatedAt.After(now.Add(futureSkew)) {
		return errors.New("invalid queue timestamp")
	}
	if q.Items == nil || len(q.Items) > maxQueueItems || q.Omitted < 0 || q.Omitted > 10000 {
		return errors.New("invalid queue size")
	}
	seen, recommended := map[string]bool{}, 0
	for _, it := range q.Items {
		if !slug.MatchString(it.ID) || seen[it.ID] {
			return errors.New("invalid or duplicate queue task id")
		}
		seen[it.ID] = true
		if !textOK(it.Title, 120, false) || !textOK(it.Summary, 560, false) || !queueStates[it.State] {
			return errors.New("invalid queue task " + it.ID)
		}
		if it.BlockedBy != "" && (it.State != "Blocked" || !textOK(it.BlockedBy, 120, false)) {
			return errors.New("invalid blocker for queue task " + it.ID)
		}
		if it.Recommended {
			recommended++
		}
	}
	if recommended > 1 {
		return errors.New("at most one recommended queue task")
	}
	return nil
}

// readQueue returns nil when the queue is absent or invalid, like other evidence.
func (r roots) readQueue(id string, now time.Time) *queueDisplay {
	raw, err := feedFile(r.feed, id, kindQueue)
	if err != nil {
		return nil
	}
	q, err := decodeQueue(raw)
	if err != nil || q.validate(id, now) != nil {
		return nil
	}
	return &queueDisplay{q.UpdatedAt, now.Sub(q.UpdatedAt) > queueTTL, q.Items, q.Omitted}
}

func (r roots) publishQueue(input io.Reader, apply bool, now time.Time) error {
	raw, err := io.ReadAll(io.LimitReader(input, maxQueue+1))
	if err != nil {
		return errors.New("could not read queue")
	}
	q, err := decodeQueue(raw)
	if err != nil {
		return err
	}
	id := q.Project
	if projects.name(id) == "" {
		return errors.New("unknown project")
	}
	return r.publishFile(raw, id, kindQueue, apply, func() error {
		if err := q.validate(id, now); err != nil {
			return err
		}
		previous, err := feedFile(r.feed, id, kindQueue)
		if err == nil {
			prev, e := decodeQueue(previous)
			if e != nil || prev.Schema != queueSchema || prev.Project != id || prev.UpdatedAt.IsZero() {
				return errors.New("existing queue is invalid; inspect manually")
			}
			if !q.UpdatedAt.After(prev.UpdatedAt) {
				return errors.New("queue must be later than the published one")
			}
		} else if !missing(err) {
			return errors.New("existing queue cannot be trusted")
		}
		return nil
	})
}
