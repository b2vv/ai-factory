package main

import (
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func useProjects(t *testing.T, list ...projectConfig) {
	t.Helper()
	g, err := newRegistry(list, "")
	if err != nil {
		t.Fatal(err)
	}
	old := projects
	projects = g
	t.Cleanup(func() { projects = old })
}

func TestProjectsConfig(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "projects.json")
	put := func(raw string) {
		t.Helper()
		if err := os.WriteFile(path, []byte(raw), 0600); err != nil {
			t.Fatal(err)
		}
	}
	valid := `[{"id":"project-a","name":"Project A","root":"/srv/project-a","aliases":[{"id":"project-a-t1","task":"t1"}]},` +
		`{"id":"project-b","name":"Project B","root":"/srv/checkouts/project-b","workflow":"Review, then QA."}]`
	put(valid)
	g, err := loadProjects(path, "")
	if err != nil {
		t.Fatal(err)
	}
	if strings.Join(g.ids, ",") != "project-a,project-b" || g.root("project-b") != "/srv/checkouts/project-b" ||
		g.name("project-a") != "Project A" || g.details["project-a-t1"] != "project-a" || g.aliases["project-a-t1"] != "t1" ||
		g.byID["project-b"].Workflow == "" || g.name("unknown") != "" {
		t.Fatalf("unexpected registry: %+v", g)
	}
	g, err = loadProjects(path, "/inputs/projects")
	if err != nil || g.root("project-a") != "/inputs/projects/project-a" {
		t.Fatalf("roots-under not applied: %v %+v", err, g)
	}
	if _, err := loadProjects(path, "inputs"); err == nil {
		t.Fatal("accepted relative roots-under")
	}
	if example, err := filepath.Abs("projects.example.json"); err != nil {
		t.Fatal(err)
	} else if _, err := loadProjects(example, ""); err != nil {
		t.Fatalf("shipped example is invalid: %v", err)
	}

	entry := func(id, root string) string { return fmt.Sprintf(`{"id":%q,"name":"N","root":%q}`, id, root) }
	many := make([]string, maxProjects+1)
	for i := range many {
		many[i] = entry(fmt.Sprintf("p%d", i), "/srv/p")
	}
	for _, raw := range []string{
		``, `{}`, `null`, `[]`, `"x"`, valid + `[]`,
		`[` + strings.Join(many, ",") + `]`,
		`[{"id":"a","name":"N","root":"/srv/a","extra":1}]`,
		`[{"id":"a","id":"b","name":"N","root":"/srv/a"}]`,
		`[{"name":"N","root":"/srv/a"}]`,
		`[` + entry("a", "/srv/a") + `,` + entry("a", "/srv/b") + `]`,
		`[` + entry("A", "/srv/a") + `]`, `[` + entry("-a", "/srv/a") + `]`, `[` + entry("a_b", "/srv/a") + `]`,
		`[` + entry("a.b", "/srv/a") + `]`, `[` + entry(strings.Repeat("a", 64), "/srv/a") + `]`,
		`[` + entry("a", "srv/a") + `]`, `[` + entry("a", "") + `]`, `[` + entry("a", "/") + `]`,
		`[` + entry("a", "/srv/../etc") + `]`, `[` + entry("a", "/srv/a/") + `]`, `[` + entry("a", "/srv/a,b") + `]`,
		`[` + entry("a", "/srv/a\nb") + `]`, `[` + entry("a", "/srv/a\"b") + `]`,
		`[{"id":"a","name":"/private/path","root":"/srv/a"}]`, `[{"id":"a","name":"","root":"/srv/a"}]`,
		`[{"id":"a","name":"N","root":"/srv/a","workflow":"see https://example.invalid"}]`,
		`[{"id":"a","name":"N","root":"/srv/a","aliases":[{"id":"a","task":"t"}]}]`,
		`[{"id":"a","name":"N","root":"/srv/a","aliases":[{"id":"x","task":"t"},{"id":"x","task":"u"}]}]`,
		`[{"id":"a","name":"N","root":"/srv/a","aliases":[{"id":"x","task":"Bad Task"}]}]`,
		`[{"id":"a","name":"N","root":"/srv/a"}]` + strings.Repeat(" ", maxProjectsConfig),
	} {
		put(raw)
		if _, err := loadProjects(path, ""); err == nil {
			t.Fatalf("accepted invalid projects config %.120q", raw)
		}
	}
	put(valid)
	link := filepath.Join(dir, "link.json")
	if err := os.Symlink(path, link); err != nil {
		t.Fatal(err)
	}
	for _, invalid := range []string{"", "projects.json", link, dir, filepath.Join(dir, "missing.json"), dir + "/./projects.json"} {
		if _, err := loadProjects(invalid, ""); err == nil {
			t.Fatalf("accepted config path %q", invalid)
		}
	}
}
