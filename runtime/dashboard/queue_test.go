package main

import (
	"bytes"
	"context"
	"encoding/json"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

func queueFixture(now time.Time) queueRecord {
	return queueRecord{Schema: queueSchema, Project: "project-a", UpdatedAt: now, Omitted: 0, Items: []queueItem{
		{ID: "t24", Title: "Open tasks on the card", State: "In progress", Summary: "Shows every open task.", Recommended: true},
		{ID: "t08", Title: "Dashboard hardening", State: "Blocked", Summary: "Header and wiring checks.", BlockedBy: "T05"},
	}}
}

func queueBody(t *testing.T, q queueRecord) []byte {
	t.Helper()
	raw, err := json.Marshal(q)
	if err != nil {
		t.Fatal(err)
	}
	return raw
}

func TestQueueRules(t *testing.T) {
	useProjects(t, projectConfig{ID: "project-a", Name: "Project A", Root: t.TempDir()})
	now := time.Now().UTC().Truncate(time.Second)
	if err := queueFixture(now).validate("project-a", now); err != nil {
		t.Fatal(err)
	}
	empty := queueFixture(now)
	empty.Items = []queueItem{}
	if err := empty.validate("project-a", now); err != nil {
		t.Fatalf("an empty list clears the queue: %v", err)
	}
	many := make([]queueItem, maxQueueItems+1)
	for i := range many {
		many[i] = queueItem{ID: "t" + strings.Repeat("1", i%40+1) + string(rune('a'+i/40)), Title: "T", State: "Ready", Summary: "S"}
	}
	cases := map[string]func(*queueRecord){
		"schema":            func(q *queueRecord) { q.Schema = feedSchema },
		"unknown project":   func(q *queueRecord) { q.Project = "project-z" },
		"future":            func(q *queueRecord) { q.UpdatedAt = now.Add(time.Minute) },
		"missing items":     func(q *queueRecord) { q.Items = nil },
		"65 items":          func(q *queueRecord) { q.Items = many },
		"negative omitted":  func(q *queueRecord) { q.Omitted = -1 },
		"bad id":            func(q *queueRecord) { q.Items[0].ID = "T24" },
		"duplicate id":      func(q *queueRecord) { q.Items[1].ID = "t24" },
		"title 121 bytes":   func(q *queueRecord) { q.Items[0].Title = strings.Repeat("a", 121) },
		"summary 561 bytes": func(q *queueRecord) { q.Items[0].Summary = strings.Repeat("a", 561) },
		"bad state":         func(q *queueRecord) { q.Items[0].State = "Done" },
		"blocker not Blocked": func(q *queueRecord) {
			q.Items[0].BlockedBy = "T05"
		},
		"two recommended": func(q *queueRecord) { q.Items[1].Recommended = true },
		"path in summary": func(q *queueRecord) { q.Items[0].Summary = "edit /etc/hosts" },
		"URL in title":    func(q *queueRecord) { q.Items[0].Title = "see https://example.test" },
		"blank summary":   func(q *queueRecord) { q.Items[0].Summary = "  " },
	}
	for name, change := range cases {
		q := queueFixture(now)
		q.Items = append([]queueItem(nil), q.Items...)
		change(&q)
		if q.validate("project-a", now) == nil {
			t.Errorf("%s accepted", name)
		}
	}
	for name, raw := range map[string]string{
		"unknown member":      `{"schema":"factory-dashboard/queue/1","project":"project-a","updatedAt":"2026-01-01T00:00:00Z","items":[],"omitted":0,"extra":1}`,
		"unknown item member": `{"schema":"factory-dashboard/queue/1","project":"project-a","updatedAt":"2026-01-01T00:00:00Z","items":[{"id":"t1","title":"T","state":"Ready","summary":"S","owner":"x"}],"omitted":0}`,
		"over 32 KiB":         `{"schema":"factory-dashboard/queue/1","project":"` + strings.Repeat("a", maxQueue) + `"}`,
	} {
		if _, err := decodeQueue([]byte(raw)); err == nil {
			t.Errorf("%s decoded", name)
		}
	}
}

func TestQueuePublishAndRead(t *testing.T) {
	useProjects(t, projectConfig{ID: "project-a", Name: "Project A", Root: t.TempDir()})
	feed := t.TempDir()
	if err := os.Chmod(feed, 0700); err != nil {
		t.Fatal(err)
	}
	r := roots{feed: feed}
	now := time.Now().UTC().Truncate(time.Second)
	raw := queueBody(t, queueFixture(now))
	if err := r.publishQueue(bytes.NewReader(raw), false, now); err != nil {
		t.Fatal(err)
	}
	if _, err := os.Stat(filepath.Join(feed, "project-a.queue.json")); !os.IsNotExist(err) {
		t.Fatal("dry run wrote the queue")
	}
	if err := r.publishQueue(bytes.NewReader(raw), true, now); err != nil {
		t.Fatal(err)
	}
	info, err := os.Stat(filepath.Join(feed, "project-a.queue.json"))
	if err != nil || info.Mode().Perm() != 0600 {
		t.Fatalf("queue file: %v %v", info, err)
	}
	if err := r.publishQueue(bytes.NewReader(raw), true, now); err == nil {
		t.Fatal("a queue not newer than the published one was accepted")
	}
	got := r.readQueue("project-a", now)
	if got == nil || got.Stale || len(got.Items) != 2 || got.Items[0].ID != "t24" {
		t.Fatalf("read: %+v", got)
	}
	if late := r.readQueue("project-a", now.Add(queueTTL+time.Hour)); late == nil || !late.Stale {
		t.Fatalf("stale: %+v", late)
	}
	// The queue rides on the card whatever the status record says (here: no status at all).
	card, _ := r.readOne("project-a", now)
	if card.Queue == nil || card.Queue.Items[1].BlockedBy != "T05" {
		t.Fatalf("card: %+v", card.Queue)
	}
	// A clearing publish shows an empty list, encoded as [] for the UI.
	empty := queueFixture(now.Add(time.Second))
	empty.Items = []queueItem{}
	if err := r.publishQueue(bytes.NewReader(queueBody(t, empty)), true, now.Add(time.Second)); err != nil {
		t.Fatal(err)
	}
	out, _ := json.Marshal(r.readQueue("project-a", now.Add(time.Second)))
	if !strings.Contains(string(out), `"items":[]`) {
		t.Fatalf("empty list: %s", out)
	}
	// An invalid file is ignored like other evidence.
	if err := os.WriteFile(filepath.Join(feed, "project-a.queue.json"), []byte("{}"), 0600); err != nil {
		t.Fatal(err)
	}
	if r.readQueue("project-a", now) != nil {
		t.Fatal("invalid queue shown")
	}
}

func TestOwnerStatusCarriesQueue(t *testing.T) {
	useProjects(t, projectConfig{ID: "project-a", Name: "Project A", Root: "/srv/project-a"})
	read := func() snapshot {
		return snapshot{Projects: []project{{ID: "project-a", Queue: &queueDisplay{Items: []queueItem{{ID: "t1", Title: "Queue title", State: "Ready", Summary: "S"}}}}}}
	}
	h := dashboard("127.0.0.1:8732", func(_ context.Context) snapshot { return read() }, nil)
	req := httptest.NewRequest("GET", "http://127.0.0.1:8732/api/status", nil)
	req.Host = "127.0.0.1:8732"
	w := httptest.NewRecorder()
	h.ServeHTTP(w, req)
	if w.Code != 200 || !strings.Contains(w.Body.String(), "Queue title") {
		t.Fatalf("%d %s", w.Code, w.Body)
	}
}
