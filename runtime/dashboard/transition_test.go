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

func TestTransitionKeepsCuratedBytesAndExactScope(t *testing.T) {
	for _, test := range []struct {
		name, schema, task, slice, stamp string
		invalid, stale, keep             bool
	}{
		{"exact slice", "v2", "099", "3a", "a", false, false, true},
		{"same head different slice", "v2", "099", "3b", "a", false, false, false},
		{"same head changed dirty scope", "v2", "099", "3a", "b", false, false, false},
		{"same head different task", "v2", "100", "3a", "a", false, false, false},
		{"unbound", "v2", "099", "", "", false, false, false},
		{"old v1 lacks scope proof", "v1", "099", "3a", "a", false, false, false},
		{"present malformed", "v2", "099", "3a", "a", true, false, false},
		{"present expired", "v2", "099", "3a", "a", false, true, false},
	} {
		t.Run(test.name, func(t *testing.T) {
			now := time.Now().UTC()
			useProjects(t, projectConfig{ID: "project-a", Name: "Project A", Root: t.TempDir(), Aliases: []projectAlias{{"project-a-099", "099"}}})
			r := roots{feed: t.TempDir()}
			if err := os.Chmod(r.feed, 0700); err != nil {
				t.Fatal(err)
			}
			f := fixture(now.Add(-time.Minute))
			f.TaskID = "099"
			if test.schema == "v2" {
				f.Schema = scopedFeedSchema
				f.ScopeID = "3a"
				f.ScopeSnapshot = strings.Repeat("a", 64)
			}
			writeHead(t, r.repo("project-a"), f.Revision)
			want := body(t, f)
			if err := r.publish(bytes.NewReader(want), true, now); err != nil {
				t.Fatal(err)
			}
			without, _ := r.readOne("project-a", now)
			if test.schema == "v2" && (without.State != "Unknown" || without.DetailToken != "") {
				t.Fatal("scoped gates appeared without active transition")
			}
			if test.schema == "v1" && (without.DetailToken == "" || !strings.Contains(without.Provenance, "без прив’язки")) {
				t.Fatal("legacy view unavailable or not explicitly labeled")
			}
			primary := filepath.Join(r.feed, "project-a.json")
			original, err := os.Stat(primary)
			if err != nil {
				t.Fatal(err)
			}
			tr := transitionRecord{Schema: transitionSchema, Project: "project-a", Revision: f.Revision, TaskID: test.task,
				Event: "stage", Stage: "review", UpdatedAt: now, RecordedAt: now.Add(-time.Second), ScopeID: test.slice, ScopeSnapshot: strings.Repeat(test.stamp, 64)}
			trRaw, err := json.Marshal(tr)
			if err != nil {
				t.Fatal(err)
			}
			transitionPath := filepath.Join(r.feed, "project-a.transition.json")
			if test.invalid || test.stale {
				if test.invalid {
					trRaw = []byte("{invalid")
				} else {
					tr.UpdatedAt = now.Add(-feedTTL - time.Minute)
					tr.RecordedAt = tr.UpdatedAt
					trRaw, err = json.Marshal(tr)
					if err != nil {
						t.Fatal(err)
					}
				}
				if err := os.WriteFile(transitionPath, trRaw, 0600); err != nil {
					t.Fatal(err)
				}
			} else {
				if err := r.publishTransition(bytes.NewReader(trRaw), false, now); err != nil {
					t.Fatal(err)
				}
				if _, err := os.Stat(transitionPath); !os.IsNotExist(err) {
					t.Fatal("dry-run wrote transition")
				}
				if err := r.publishTransition(bytes.NewReader(trRaw), true, now); err != nil {
					t.Fatal(err)
				}
				if err := r.publishTransition(bytes.NewReader(trRaw), true, now); err == nil {
					t.Fatal("replayed transition")
				}
			}
			got, err := os.ReadFile(primary)
			if err != nil || !bytes.Equal(got, want) {
				t.Fatal("curated bytes changed")
			}
			still, err := os.Stat(primary)
			if err != nil || !os.SameFile(original, still) || !still.ModTime().Equal(original.ModTime()) {
				t.Fatal("curated identity/time changed")
			}
			p, _ := r.readOne("project-a", now)
			if test.keep {
				if p.Observed != f.UpdatedAt.Format(time.RFC3339) || p.Stages[0].State != "Accepted" || p.Stages[3].State != "Unknown" || p.Transition == nil || !p.Transition.Bound {
					t.Fatalf("wrong scoped merge: %+v", p)
				}
			} else {
				if p.State != "Unknown" || p.DetailToken != "" {
					t.Fatalf("old gates revived: %+v", p)
				}
				for _, stage := range p.Stages {
					if stage.State != "Unknown" {
						t.Fatal("old gate leaked into current stage")
					}
				}
			}
			h := dashboard("127.0.0.1:8732", func(context.Context) snapshot { return snapshot{} }, func(id string) (project, feedRecord) { return r.readOne(id, now) })
			for _, route := range []string{"/api/details/project-a", "/api/details/project-a-099"} {
				w := httptest.NewRecorder()
				h.ServeHTTP(w, httptest.NewRequest("GET", "http://127.0.0.1:8732"+route, nil))
				if test.keep && w.Code != 200 || !test.keep && w.Code != 404 {
					t.Fatalf("%s result %d", route, w.Code)
				}
			}
		})
	}
}
func TestTransitionRejectsGateAndConfusedSchema(t *testing.T) {
	now := time.Now().UTC()
	useProjects(t, projectConfig{ID: "project-a", Name: "Project A", Root: t.TempDir()})
	r := roots{feed: t.TempDir()}
	head := strings.Repeat("a", 40)
	writeHead(t, r.repo("project-a"), head)
	tr := transitionRecord{Schema: transitionSchema, Project: "project-a", Revision: head, TaskID: "099", Event: "handoff", UpdatedAt: now, RecordedAt: now}
	content, err := json.Marshal(tr)
	if err != nil {
		t.Fatal(err)
	}
	if err := r.publishTransition(bytes.NewReader(content), false, now); err != nil {
		t.Fatal(err)
	}
	if err := r.publish(bytes.NewReader(content), false, now); err == nil {
		t.Fatal("transition accepted in curated writer")
	}
	for _, edit := range []func(*transitionRecord){
		func(x *transitionRecord) { x.Event = "acknowledged" },
		func(x *transitionRecord) { x.Event = "stage"; x.Stage = "pass" },
		func(x *transitionRecord) { x.Event = "stage"; x.Stage = "review"; x.ScopeID = "3a" },
		func(x *transitionRecord) { x.Revision = strings.Repeat("b", 40) },
	} {
		x := tr
		edit(&x)
		raw, err := json.Marshal(x)
		if err != nil {
			t.Fatal(err)
		}
		if err := r.publishTransition(bytes.NewReader(raw), false, now); err == nil {
			t.Fatal("invalid transition accepted")
		}
	}
	raw := append(append([]byte(nil), content[:len(content)-1]...), []byte(`,"state":"PASS"}`)...)
	if err := r.publishTransition(bytes.NewReader(raw), false, now); err == nil {
		t.Fatal("gate state accepted in transition")
	}
}
