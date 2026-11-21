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

func writeHead(t *testing.T, repo, id string) {
	t.Helper()
	if err := os.MkdirAll(filepath.Join(repo, ".git"), 0700); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(repo, ".git", "HEAD"), []byte(id+"\n"), 0600); err != nil {
		t.Fatal(err)
	}
}
func fixture(now time.Time) feedRecord {
	p := feedRecord{Schema: feedSchema, Project: "project-a", Revision: strings.Repeat("a", 40), TaskID: "task-a1", Title: "Fixture", State: "Plan accepted", UpdatedAt: now, Next: "Review plan", Markdown: "### Reviewed detail",
		Sources: []source{{"one", "plan-review", "review-recorded", "work/plan.md", now.Add(-time.Hour)}}}
	for _, n := range stageNames {
		p.Stages = append(p.Stages, feedStage{n, "Unknown", "No result", ""})
	}
	p.Stages[0] = feedStage{"Plan", "Accepted", "Ready per recorded plan review", "one"}
	return p
}
func body(t *testing.T, p feedRecord) []byte {
	t.Helper()
	b, err := json.Marshal(p)
	if err != nil {
		t.Fatal(err)
	}
	return b
}
func TestRejectUntrustedStatus(t *testing.T) {
	useProjects(t, projectConfig{ID: "project-a", Name: "Project A", Root: t.TempDir()})
	now := time.Now().UTC()
	for _, tc := range []struct {
		name string
		edit func(*feedRecord)
	}{
		{"bad project", func(p *feedRecord) { p.Project = "other" }},
		{"bad schema", func(p *feedRecord) { p.Schema = "2" }},
		{"wrong head", func(p *feedRecord) { p.Revision = strings.Repeat("b", 40) }},
		{"stale", func(p *feedRecord) { p.UpdatedAt = now.Add(-feedTTL - time.Second) }},
		{"future", func(p *feedRecord) { p.UpdatedAt = now.Add(futureSkew + time.Second) }},
		{"future source", func(p *feedRecord) { p.Sources[0].RecordedAt = now.Add(time.Second) }},
		{"stage inference", func(p *feedRecord) { p.State = "Verified locally" }},
		{"fake final review", func(p *feedRecord) { p.Stages[3] = feedStage{"Review", "Accepted", "PASS", "one"} }},
		{"fake push", func(p *feedRecord) { p.Stages[4] = feedStage{"Push", "Recorded", "pushed", "one"} }},
		{"bad provenance", func(p *feedRecord) { p.Sources[0].Role = "author-recorded" }},
		{"file location", func(p *feedRecord) { p.Sources[0].Label = "/home/example/private" }},
		{"URL source", func(p *feedRecord) { p.Sources[0].Label = "https://example.invalid/private" }},
		{"transcript size", func(p *feedRecord) { p.Markdown = strings.Repeat("a", maxDetails+1) }},
	} {
		t.Run(tc.name, func(t *testing.T) {
			p := fixture(now)
			tc.edit(&p)
			if p.validate("project-a", strings.Repeat("a", 40), now) == nil {
				t.Fatal("accepted invalid status")
			}
		})
	}
	p := fixture(now)
	if err := p.validate("project-a", p.Revision, now); err != nil {
		t.Fatal(err)
	}
	for _, raw := range [][]byte{
		[]byte(`{"title":"a","TITLE":"b"}`),
		[]byte(`{"ſchema":"wrong"}`),
		[]byte(`{"Title":"a"}`),
		[]byte(`{"nested":{"id":"a","id":"b"}}`),
		[]byte(`{"schema":"wrong","privateField":"bad"}`),
		append(body(t, p), []byte("{}")...),
		bytes.Repeat([]byte("a"), maxFeed+1),
	} {
		if _, err := decodeRecord(raw); err == nil {
			t.Fatal("accepted invalid wire")
		}
	}
}
func TestAtomicPublisherAndDynamicRoute(t *testing.T) {
	now := time.Now().UTC()
	const aliasRoute = "/api/details/project-a-task-a1"
	useProjects(t, projectConfig{ID: "project-a", Name: "Project A", Root: t.TempDir(), Aliases: []projectAlias{{"project-a-task-a1", "task-a1"}}},
		projectConfig{ID: "project-b", Name: "Project B", Root: t.TempDir()})
	r := roots{feed: t.TempDir()}
	if err := os.Chmod(r.feed, 0700); err != nil {
		t.Fatal(err)
	}
	p := fixture(now)
	writeHead(t, r.repo("project-a"), p.Revision)
	if err := r.publish(bytes.NewReader(body(t, p)), false, now); err != nil {
		t.Fatal(err)
	}
	if _, err := os.Stat(filepath.Join(r.feed, "project-a.json")); !os.IsNotExist(err) {
		t.Fatal("dry run touched feed")
	}
	if err := r.publish(bytes.NewReader(body(t, p)), true, now); err != nil {
		t.Fatal(err)
	}
	dst, err := os.Stat(filepath.Join(r.feed, "project-a.json"))
	if err != nil || dst.Mode().Perm() != 0600 {
		t.Fatal("wrong published mode")
	}
	h := dashboard("127.0.0.1:8732", func(context.Context) snapshot { return r.snapshot() }, func(id string) (project, feedRecord) { return r.readOne(id, now.Add(time.Second)) })
	get := func(url string) (int, string, string) {
		w := httptest.NewRecorder()
		h.ServeHTTP(w, httptest.NewRequest("GET", "http://127.0.0.1:8732"+url, nil))
		return w.Code, w.Body.String(), w.Header().Get("X-Dashboard-Detail-Token")
	}
	status, txt, token := get(aliasRoute)
	if status != 200 || txt != p.Markdown || token == "" {
		t.Fatal("initial detail not delivered")
	}
	for _, path := range []string{"/api/details/project-b", "/api/details/unknown", "/api/details/../../project-a", "/api/details/project-a?f=/private", "/api/details/%70roject-a", "/feed/project-a.json"} {
		if code, _, _ := get(path); code != 404 {
			t.Fatalf("unexpected access on %s: %d", path, code)
		}
	}
	p.UpdatedAt = now.Add(time.Second)
	p.Markdown = "### After atomic publish"
	p.TaskID = "new-task"
	if err := r.publish(bytes.NewReader(body(t, p)), true, now.Add(time.Second)); err != nil {
		t.Fatal(err)
	}
	status, txt, nextToken := get("/api/details/project-a")
	if status != 200 || txt != p.Markdown || nextToken == "" || nextToken == token {
		t.Fatal("same process did not reload update")
	}
	if code, _, _ := get(aliasRoute); code != 404 {
		t.Fatal("old task alias showed the new task")
	}
	if err := r.publish(bytes.NewReader(body(t, p)), true, now.Add(time.Second)); err == nil {
		t.Fatal("replayed old timestamp")
	}
	writeHead(t, r.repo("project-a"), strings.Repeat("b", 40))
	if code, _, _ := get("/api/details/project-a"); code != 404 {
		t.Fatal("mismatched HEAD exposed details")
	}
	if card, _ := r.readOne("project-a", now.Add(time.Second)); card.State != "Unknown" {
		t.Fatal("stale record did not go Unknown")
	}
}
