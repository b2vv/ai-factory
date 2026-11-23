package main

import (
	"errors"
	"io"
	"regexp"
	"time"
)

const transitionSchema = "factory-dashboard/transition/1"
const scopedFeedSchema = "factory-dashboard/status/2"

var scopeDigest = regexp.MustCompile(`^[a-f0-9]{64}$`)

type transitionRecord struct {
	Schema        string    `json:"schema"`
	Project       string    `json:"project"`
	Revision      string    `json:"revision"`
	TaskID        string    `json:"taskId"`
	Event         string    `json:"event"`
	Stage         string    `json:"stage,omitempty"`
	UpdatedAt     time.Time `json:"updatedAt"`
	RecordedAt    time.Time `json:"recordedAt"`
	ScopeID       string    `json:"scopeId,omitempty"`
	ScopeSnapshot string    `json:"scopeSnapshot,omitempty"`
}
type transitionDisplay struct {
	Text       string    `json:"text"`
	UpdatedAt  time.Time `json:"updatedAt"`
	RecordedAt time.Time `json:"recordedAt"`
	Bound      bool      `json:"bound"`
}

var displayEvent = map[string]string{
	"start":    "Зафіксовано початок",
	"stage":    "Зафіксовано перехід етапу",
	"handoff":  "Зафіксовано етап передачі",
	"closeout": "Зафіксовано підбиття підсумків",
}
var displayStage = map[string]string{
	"plan": "планування", "implementation": "реалізація", "verification": "перевірка", "review": "рев’ю", "qa": "QA", "push": "push", "update": "оновлення",
}

func validScope(id, snapshot string) bool {
	return slug.MatchString(id) && scopeDigest.MatchString(snapshot)
}
func fresh(updated, now time.Time) bool {
	return !updated.IsZero() && !updated.Before(now.Add(-feedTTL)) && !updated.After(now.Add(futureSkew))
}
func (t transitionRecord) validate(id, head string, now time.Time) error {
	if t.Schema != transitionSchema || projects.name(id) == "" || t.Project != id || !slug.MatchString(t.TaskID) {
		return errors.New("invalid transition schema/project/task")
	}
	if !revisionPattern.MatchString(head) || t.Revision != head {
		return errors.New("transition revision not current")
	}
	if !fresh(t.UpdatedAt, now) || t.RecordedAt.IsZero() || t.RecordedAt.After(t.UpdatedAt) {
		return errors.New("invalid transition timestamps")
	}
	if displayEvent[t.Event] == "" || t.Event == "stage" && displayStage[t.Stage] == "" || t.Event != "stage" && t.Stage != "" {
		return errors.New("invalid transition event or stage")
	}
	if (t.ScopeID != "" || t.ScopeSnapshot != "") && !validScope(t.ScopeID, t.ScopeSnapshot) {
		return errors.New("incomplete transition scope")
	}
	return nil
}
func (t transitionRecord) applicable(f feedRecord) bool {
	return f.Schema == scopedFeedSchema && validScope(t.ScopeID, t.ScopeSnapshot) &&
		t.Project == f.Project && t.Revision == f.Revision && t.TaskID == f.TaskID && t.ScopeID == f.ScopeID && t.ScopeSnapshot == f.ScopeSnapshot
}
func (t transitionRecord) display(bound bool) *transitionDisplay {
	label := displayEvent[t.Event]
	if t.Stage != "" {
		label += ": " + displayStage[t.Stage]
	}
	return &transitionDisplay{label, t.UpdatedAt, t.RecordedAt, bound}
}
func (r roots) publishTransition(input io.Reader, apply bool, now time.Time) error {
	raw, err := io.ReadAll(io.LimitReader(input, maxFeed+1))
	if err != nil {
		return errors.New("could not read transition")
	}
	t, err := decodeBounded[transitionRecord](raw, maxFeed, canonicalField)
	if err != nil {
		return err
	}
	id := t.Project
	if projects.name(id) == "" {
		return errors.New("unknown project")
	}
	return r.publishFile(raw, id, kindTransition, apply, func() error {
		if err := t.validate(id, revision(r.repo(id)), now); err != nil {
			return err
		}
		previous, err := feedFile(r.feed, id, kindTransition)
		if err == nil {
			prev, e := decodeBounded[transitionRecord](previous, maxFeed, canonicalField)
			if e != nil || prev.Schema != transitionSchema || prev.Project != id || prev.UpdatedAt.IsZero() {
				return errors.New("existing transition is invalid; inspect manually")
			}
			if !t.UpdatedAt.After(prev.UpdatedAt) {
				return errors.New("transition must be later than existing observation")
			}
		} else if !missing(err) {
			return errors.New("existing transition cannot be trusted")
		}
		return nil
	})
}
