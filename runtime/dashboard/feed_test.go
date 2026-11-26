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
	// A moved HEAD keeps the last record readable, marked Stale with the commit it was recorded for.
	if code, txt, _ := get("/api/details/project-a"); code != 200 || txt != p.Markdown {
		t.Fatal("stale record lost its details")
	}
	card, rec := r.readOne("project-a", now.Add(time.Second))
	if card.State != "Stale" || card.DetailToken == "" || rec.Project != "project-a" ||
		!strings.Contains(card.Provenance, "не підтверджують поточний стан") {
		t.Fatalf("stale record must show as Stale with its last details: %+v", card)
	}
	for i, st := range card.Stages {
		if st.State != p.Stages[i].State {
			t.Fatal("stale card did not keep the recorded stage")
		}
	}
}

func TestStaleCard(t *testing.T) {
	now := time.Now().UTC()
	head, other := strings.Repeat("a", 40), strings.Repeat("c", 40)
	setup := func(t *testing.T, p feedRecord, headNow string) roots {
		t.Helper()
		useProjects(t, projectConfig{ID: "project-a", Name: "Project A", Root: t.TempDir()})
		r := roots{feed: t.TempDir()}
		writeHead(t, r.repo("project-a"), headNow)
		raw, err := json.Marshal(p)
		if err != nil {
			t.Fatal(err)
		}
		if err := os.WriteFile(filepath.Join(r.feed, "project-a.json"), raw, 0600); err != nil {
			t.Fatal(err)
		}
		return r
	}
	// A non-current card keeps the recorded stages and says they are not the current state.
	lastKnown := func(t *testing.T, c project) {
		t.Helper()
		want := fixture(now).Stages
		for i, st := range c.Stages {
			if st.State != want[i].State || st.Detail != want[i].Detail {
				t.Fatalf("stage %s shown as %s, recorded %s", st.Name, st.State, want[i].State)
			}
		}
		if !strings.Contains(c.Provenance, "коміту aaaaaaa") || !strings.Contains(c.Provenance, "не підтверджують поточний стан") {
			t.Fatalf("non-current card does not say its stages are not current: %q", c.Provenance)
		}
	}
	t.Run("revision moved", func(t *testing.T) {
		r := setup(t, fixture(now), other)
		c, rec := r.readOne("project-a", now)
		if c.State != "Stale" || c.Task != "Fixture" || rec.Project != "project-a" ||
			!strings.Contains(c.Next, "коміту aaaaaaa; HEAD відтоді змінився") || !strings.Contains(c.Next, "Review plan") {
			t.Fatalf("unexpected card: %+v", c)
		}
		lastKnown(t, c)
	})
	t.Run("too old", func(t *testing.T) {
		p := fixture(now.Add(-feedTTL - time.Minute))
		r := setup(t, p, head)
		c, _ := r.readOne("project-a", now)
		if c.State != "Stale" || !strings.Contains(c.Next, "понад 48 год тому") {
			t.Fatalf("unexpected card: %+v", c)
		}
		lastKnown(t, c)
	})
	t.Run("both: revision reason first", func(t *testing.T) {
		r := setup(t, fixture(now.Add(-feedTTL-time.Minute)), other)
		if c, _ := r.readOne("project-a", now); c.State != "Stale" || !strings.Contains(c.Next, "HEAD відтоді змінився") {
			t.Fatalf("unexpected card: %+v", c)
		}
	})
	t.Run("unreadable HEAD says so", func(t *testing.T) {
		r := setup(t, fixture(now), "not-a-sha")
		if c, _ := r.readOne("project-a", now); c.State != "Stale" || !strings.Contains(c.Next, "поточний HEAD не прочитано") {
			t.Fatalf("unexpected card: %+v", c)
		}
	})
	t.Run("current record unchanged", func(t *testing.T) {
		r := setup(t, fixture(now), head)
		if c, rec := r.readOne("project-a", now); c.State != "Plan accepted" || rec.Project != "project-a" {
			t.Fatalf("current record changed: %+v", c)
		}
	})
	bare := []struct {
		name string
		edit func(*feedRecord)
	}{
		{"path in next", func(p *feedRecord) { p.Next = "see /home/example/secret-plan.md" }},
		{"URL in title", func(p *feedRecord) { p.Title = "https://example.invalid/private" }},
		{"URL as revision", func(p *feedRecord) { p.Revision = "https://example.invalid/x" }},
		{"path as revision", func(p *feedRecord) { p.Revision = "../../etc/passwd" }},
		{"control chars in revision", func(p *feedRecord) { p.Revision = "aaaaaaa\x1b[31m" + strings.Repeat("a", 30) }},
		{"fake push stage", func(p *feedRecord) { p.Stages[4] = feedStage{"Push", "Recorded", "pushed", "one"} }},
		{"future dated", func(p *feedRecord) { p.UpdatedAt = now.Add(futureSkew + time.Minute) }},
	}
	for _, tc := range bare {
		t.Run("bare: "+tc.name, func(t *testing.T) {
			p := fixture(now)
			tc.edit(&p)
			r := setup(t, p, other)
			c, _ := r.readOne("project-a", now)
			out, _ := json.Marshal(c)
			if c.State != "Unknown" || c.Task != "Поточну задачу не підтверджено" ||
				strings.Contains(string(out), "example.invalid") || strings.Contains(string(out), "/home/example") || strings.Contains(string(out), "passwd") {
				t.Fatalf("invalid record rendered: %s", out)
			}
		})
	}
	t.Run("transition file keeps priority", func(t *testing.T) {
		r := setup(t, fixture(now), other)
		if err := os.WriteFile(filepath.Join(r.feed, "project-a.transition.json"), []byte("{}"), 0600); err != nil {
			t.Fatal(err)
		}
		if c, _ := r.readOne("project-a", now); c.State == "Stale" || !strings.Contains(c.Next, "Запис переходу") {
			t.Fatalf("transition path not taken: %+v", c)
		}
	})
	t.Run("share view shows Stale and nothing else", func(t *testing.T) {
		r := setup(t, fixture(now), other)
		c, _ := r.readOne("project-a", now)
		got := projectStates(snapshot{CheckedAt: now, Projects: []project{c}})
		if len(got.Projects) != 1 || got.Projects[0].State != "Stale" {
			t.Fatalf("share projection: %+v", got)
		}
		out, _ := json.Marshal(got)
		if strings.Contains(string(out), "Review plan") || strings.Contains(string(out), "Fixture") {
			t.Fatalf("share view leaked task text: %s", out)
		}
	})
}
