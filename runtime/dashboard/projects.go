package main

import (
	"bytes"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"regexp"
	"strings"
	"unicode"
	"unicode/utf8"
)

// The project list is deployment configuration. It lives outside the kit and
// is passed with -projects (or DASHBOARD_PROJECTS); the kit ships no project.
const maxProjectsConfig = 64 << 10
const maxProjects = 32
const maxAliases = 8
const maxRoot = 1024

var projectIDPattern = regexp.MustCompile(`^[a-z0-9][a-z0-9-]{0,62}$`)

type projectAlias struct {
	ID   string `json:"id"`
	Task string `json:"task"`
}

type projectConfig struct {
	ID       string         `json:"id"`
	Name     string         `json:"name"`
	Root     string         `json:"root"`
	Workflow string         `json:"workflow,omitempty"`
	Aliases  []projectAlias `json:"aliases,omitempty"`
}

type projectRegistry struct {
	ids     []string
	byID    map[string]projectConfig
	details map[string]string // detail route ID -> project ID
	aliases map[string]string // alias route ID -> task ID it is bound to
}

// projects is set once at startup, before any listener or publisher runs.
var projects projectRegistry

func (g projectRegistry) name(id string) string { return g.byID[id].Name }
func (g projectRegistry) root(id string) string { return g.byID[id].Root }

var projectConfigField = map[string]bool{"id": true, "name": true, "root": true, "workflow": true, "aliases": true, "task": true}

func validRoot(root string) bool {
	if len(root) == 0 || len(root) > maxRoot || !utf8.ValidString(root) || !filepath.IsAbs(root) ||
		filepath.Clean(root) != root || root == string(filepath.Separator) || strings.ContainsAny(root, ",\"") {
		return false
	}
	for _, c := range root {
		if unicode.IsControl(c) {
			return false
		}
	}
	return true
}

// newRegistry validates the whole list strictly; any invalid entry rejects it.
// rootsUnder, when set, replaces every root by rootsUnder/<id> (container mounts).
func newRegistry(list []projectConfig, rootsUnder string) (projectRegistry, error) {
	g := projectRegistry{byID: map[string]projectConfig{}, details: map[string]string{}, aliases: map[string]string{}}
	if rootsUnder != "" && !validRoot(rootsUnder) {
		return g, errors.New("invalid project roots base")
	}
	if len(list) == 0 || len(list) > maxProjects {
		return g, fmt.Errorf("expected 1-%d projects", maxProjects)
	}
	for _, p := range list {
		if !projectIDPattern.MatchString(p.ID) || g.details[p.ID] != "" {
			return g, errors.New("invalid or duplicate project id")
		}
		if !textOK(p.Name, 80, false) {
			return g, errors.New("invalid project name")
		}
		if !validRoot(p.Root) {
			return g, errors.New("project root must be a clean absolute path without commas, quotes or control characters")
		}
		if p.Workflow != "" && !textOK(p.Workflow, 560, false) {
			return g, errors.New("invalid project workflow note")
		}
		if len(p.Aliases) > maxAliases {
			return g, errors.New("too many project aliases")
		}
		if rootsUnder != "" {
			p.Root = filepath.Join(rootsUnder, p.ID)
		}
		g.ids = append(g.ids, p.ID)
		g.byID[p.ID] = p
		g.details[p.ID] = p.ID
	}
	for _, p := range list {
		for _, a := range p.Aliases {
			if !projectIDPattern.MatchString(a.ID) || g.details[a.ID] != "" || !slug.MatchString(a.Task) {
				return g, errors.New("invalid or duplicate project alias")
			}
			g.details[a.ID] = p.ID
			g.aliases[a.ID] = a.Task
		}
	}
	return g, nil
}

func loadProjects(path, rootsUnder string) (projectRegistry, error) {
	if !validRoot(path) {
		return projectRegistry{}, errors.New("projects config requires a clean absolute path")
	}
	dir, err := os.OpenRoot(filepath.Dir(path))
	if err != nil {
		return projectRegistry{}, err
	}
	defer dir.Close()
	f, info, err := boundedFile(dir, filepath.Base(path), maxProjectsConfig)
	if err != nil {
		return projectRegistry{}, err
	}
	defer f.Close()
	raw, err := io.ReadAll(io.LimitReader(f, maxProjectsConfig+1))
	if err != nil || int64(len(raw)) != info.Size() || len(raw) == 0 || !utf8.Valid(raw) {
		return projectRegistry{}, errors.New("could not read projects config")
	}
	if err := uniqueFields(raw, projectConfigField); err != nil {
		return projectRegistry{}, err
	}
	var list []projectConfig
	d := json.NewDecoder(bytes.NewReader(raw))
	d.DisallowUnknownFields()
	if err := d.Decode(&list); err != nil || list == nil {
		return projectRegistry{}, errors.New("projects config must be a JSON array of {id, name, root}")
	}
	if err := d.Decode(new(any)); err != io.EOF {
		return projectRegistry{}, errors.New("trailing data in projects config")
	}
	return newRegistry(list, rootsUnder)
}
