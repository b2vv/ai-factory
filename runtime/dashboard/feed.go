package main

import (
	"bytes"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"regexp"
	"strings"
	"syscall"
	"time"
	"unicode"
	"unicode/utf8"
)

const feedSchema = "factory-dashboard/status/1"
const maxFeed = 16 << 10
const maxDetails = 4 << 10
const feedTTL = 48 * time.Hour
const futureSkew = 30 * time.Second

var stageNames = [...]string{"Plan", "Implementation", "Tests", "Review", "Push", "Update"}
var slug = regexp.MustCompile(`^[a-z0-9][a-z0-9-]{0,47}$`)
var address = regexp.MustCompile(`(?i)(://|file:|~[/\\]|(?:^|[\s(\x60"'])[/\\]|[a-z]:\\|\.\.[/\\])`)

type source struct {
	ID         string    `json:"id"`
	Kind       string    `json:"kind"`
	Role       string    `json:"role"`
	Label      string    `json:"label"`
	RecordedAt time.Time `json:"recordedAt"`
}
type feedStage struct {
	Name     string `json:"name"`
	State    string `json:"state"`
	Detail   string `json:"detail"`
	SourceID string `json:"sourceId,omitempty"`
}
type feedRecord struct {
	Schema        string      `json:"schema"`
	Project       string      `json:"project"`
	Revision      string      `json:"revision"`
	TaskID        string      `json:"taskId"`
	Title         string      `json:"title"`
	State         string      `json:"state"`
	UpdatedAt     time.Time   `json:"updatedAt"`
	Next          string      `json:"next"`
	Sources       []source    `json:"sources"`
	Stages        []feedStage `json:"stages"`
	Markdown      string      `json:"markdown,omitempty"`
	ScopeID       string      `json:"scopeId,omitempty"`
	ScopeSnapshot string      `json:"scopeSnapshot,omitempty"`
}

func textOK(s string, limit int, multiline bool) bool {
	if len(s) == 0 || len(s) > limit || strings.TrimSpace(s) == "" || !utf8.ValidString(s) || address.MatchString(s) {
		return false
	}
	for _, c := range s {
		if unicode.IsControl(c) && !(multiline && c == '\n') {
			return false
		}
	}
	return true
}
func decodeRecord(raw []byte) (feedRecord, error) {
	return decodeBounded[feedRecord](raw, maxFeed, canonicalField)
}

// decodeBounded decodes one JSON object of at most limit bytes whose member names are all in allowed.
func decodeBounded[T any](raw []byte, limit int, allowed map[string]bool) (T, error) {
	var out T
	if len(raw) == 0 || len(raw) > limit || !utf8.Valid(raw) {
		return out, errors.New("record size or encoding invalid")
	}
	if err := uniqueFields(raw, allowed); err != nil {
		return out, err
	}
	d := json.NewDecoder(bytes.NewReader(raw))
	d.DisallowUnknownFields()
	if err := d.Decode(&out); err != nil {
		return out, errors.New("record is not the declared status JSON object")
	}
	if err := d.Decode(new(any)); err != io.EOF {
		return out, errors.New("trailing data")
	}
	return out, nil
}

var canonicalField = map[string]bool{
	"schema": true, "project": true, "revision": true, "taskId": true, "title": true, "state": true,
	"updatedAt": true, "next": true, "sources": true, "stages": true, "markdown": true,
	"scopeId": true, "scopeSnapshot": true, "event": true, "stage": true,
	"id": true, "kind": true, "role": true, "label": true, "recordedAt": true, "name": true, "detail": true, "sourceId": true,
}

func uniqueFields(raw []byte, allowed map[string]bool) error {
	d := json.NewDecoder(bytes.NewReader(raw))
	var value func(int) error
	value = func(depth int) error {
		if depth > 8 {
			return errors.New("JSON nesting exceeds limit")
		}
		t, err := d.Token()
		if err != nil {
			return err
		}
		mark, ok := t.(json.Delim)
		if !ok {
			return nil
		}
		switch mark {
		case '{':
			keys := map[string]bool{}
			for d.More() {
				key, err := d.Token()
				k, ok := key.(string)
				if err != nil || !ok || !allowed[k] || keys[k] {
					return errors.New("invalid or duplicate JSON member")
				}
				keys[k] = true
				if err := value(depth + 1); err != nil {
					return err
				}
			}
		case '[':
			for d.More() {
				if err := value(depth + 1); err != nil {
					return err
				}
			}
		default:
			return errors.New("invalid JSON delimiter")
		}
		_, err = d.Token()
		return err
	}
	return value(0)
}
func validStage(s feedStage, src source) bool {
	switch s.State {
	case "Unknown":
		return s.SourceID == ""
	case "Not recorded":
		return (s.Name == "Push" || s.Name == "Update") && src.Kind == "work-record"
	}
	switch s.Name {
	case "Plan":
		return s.State == "Accepted" && src.Kind == "plan-review"
	case "Implementation":
		return (s.State == "Recorded" || s.State == "Probes recorded") && src.Kind == "work-record"
	case "Tests":
		return (s.State == "Recorded pass" || s.State == "Partial evidence" || s.State == "Blocked") && src.Kind == "test-record"
	case "Review":
		return (s.State == "Final verdict not recorded" || s.State == "Plan only") && (src.Kind == "work-record" || src.Kind == "plan-review")
	case "Push":
		return s.State == "Recorded" && src.Kind == "push-receipt"
	case "Update":
		return s.State == "Recorded" && src.Kind == "update-receipt"
	}
	return false
}

// validate is the full check for a current record: content, then freshness.
func (p feedRecord) validate(id, head string, now time.Time) error {
	if err := p.validateContent(id); err != nil {
		return err
	}
	_, err := p.validateFresh(head, now)
	return err
}

// staleReason says why a content-valid record is not current.
type staleReason int

const (
	freshOK staleReason = iota
	staleRevision
	staleAge
	staleFuture
)

// validateFresh checks only what changes with time and commits: the record's revision
// against current HEAD and its observation age. Revision comes first.
func (p feedRecord) validateFresh(head string, now time.Time) (staleReason, error) {
	if p.UpdatedAt.After(now.Add(futureSkew)) {
		return staleFuture, errors.New("observation expired or future-dated")
	}
	if !revisionPattern.MatchString(head) || p.Revision != head {
		return staleRevision, errors.New("revision missing or not current")
	}
	if p.UpdatedAt.Before(now.Add(-feedTTL)) {
		return staleAge, errors.New("observation expired or future-dated")
	}
	return freshOK, nil
}

// validateContent checks everything a card could render, independent of HEAD and time:
// a record that passes it may be shown as stale without exposing unchecked text.
func (p feedRecord) validateContent(id string) error {
	if p.Schema != feedSchema && p.Schema != scopedFeedSchema || projects.name(id) == "" || p.Project != id {
		return errors.New("unknown or mismatching schema/project")
	}
	if p.Schema == scopedFeedSchema && !validScope(p.ScopeID, p.ScopeSnapshot) || p.Schema == feedSchema && (p.ScopeID != "" || p.ScopeSnapshot != "") {
		return errors.New("scope binding requires the matching schema and both values")
	}
	if !revisionPattern.MatchString(p.Revision) {
		return errors.New("revision missing or not current")
	}
	if p.UpdatedAt.IsZero() {
		return errors.New("observation expired or future-dated")
	}
	if !slug.MatchString(p.TaskID) || !textOK(p.Title, 160, false) || !textOK(p.Next, 560, false) {
		return errors.New("invalid task or next-action text")
	}
	if p.Markdown != "" && !textOK(p.Markdown, maxDetails, true) {
		return errors.New("invalid Markdown summary")
	}
	if len(p.Sources) == 0 || len(p.Sources) > 12 || len(p.Stages) != 6 {
		return errors.New("invalid source or stage count")
	}
	sources := make(map[string]source, len(p.Sources))
	for _, s := range p.Sources {
		switch s.Kind {
		case "plan-review", "work-record", "test-record", "push-receipt", "update-receipt":
		default:
			return errors.New("invalid source kind")
		}
		if !slug.MatchString(s.ID) || sources[s.ID].ID != "" || !textOK(s.Label, 180, false) || s.RecordedAt.IsZero() || s.RecordedAt.After(p.UpdatedAt) {
			return errors.New("invalid source reference/timestamp")
		}
		if s.Role != "operator-curated" && s.Role != "author-recorded" && s.Role != "review-recorded" {
			return errors.New("invalid evidence role")
		}
		if s.Kind == "plan-review" && s.Role != "review-recorded" {
			return errors.New("accepted plan requires a recorded review source")
		}
		sources[s.ID] = s
	}
	for i, s := range p.Stages {
		x := sources[s.SourceID]
		if s.Name != stageNames[i] || !textOK(s.Detail, 560, false) || s.State != "Unknown" && x.ID == "" || !validStage(s, x) {
			return fmt.Errorf("invalid %s evidence state", stageNames[i])
		}
	}
	switch p.State {
	case "Verified locally":
		if p.Stages[2].State == "Recorded pass" {
			return nil
		}
	case "Decision needed":
		if p.Stages[2].State == "Blocked" {
			return nil
		}
	case "Verification pending":
		if p.Stages[2].State == "Partial evidence" || p.Stages[2].State == "Unknown" {
			return nil
		}
	case "Plan accepted":
		if p.Stages[0].State == "Accepted" && p.Stages[1].State == "Unknown" {
			return nil
		}
	case "Recorded":
		for _, s := range p.Stages {
			if s.State != "Unknown" && s.State != "Not recorded" {
				return nil
			}
		}
	}
	return errors.New("project summary state contradicts stages")
}

// staleCard shows the last known task of a content-valid record that is no longer current.
// Stages stay Unknown and no details are offered: stale evidence is never shown as current.
func (p feedRecord) staleCard(head string, reason staleReason, workflow string) project {
	out := base(p.Project, projects.name(p.Project), p.Title, head)
	out.State, out.Observed, out.Workflow = "Stale", p.UpdatedAt.UTC().Format(time.RFC3339), workflow
	why := "Записано " + p.UpdatedAt.UTC().Format("02.01 15:04") + " UTC, понад 48 год тому."
	if reason == staleRevision {
		why = "Записано для коміту " + p.Revision[:7] + "; HEAD відтоді змінився."
		if !revisionPattern.MatchString(head) {
			why = "Записано для коміту " + p.Revision[:7] + "; поточний HEAD не прочитано."
		}
	}
	out.Next = why + " Останній відомий наступний крок: " + p.Next
	out.Provenance = "Застарілий запис: етапи не підтверджено для поточного стану."
	return out
}

func digestBytes(raw []byte) string {
	id := sha256.Sum256(raw)
	return hex.EncodeToString(id[:])
}
func (p feedRecord) card(head, token string) project {
	out := base(p.Project, projects.name(p.Project), p.Title, head)
	out.State, out.Observed, out.Next = p.State, p.UpdatedAt.UTC().Format(time.RFC3339), p.Next
	if out.State == "Verified locally" {
		out.State = "Recorded"
	}
	if p.Markdown != "" {
		out.DetailID, out.DetailToken = p.Project, token
	}
	for i, v := range p.Stages {
		ref := ""
		for _, s := range p.Sources {
			if v.SourceID == s.ID {
				role := map[string]string{"operator-curated": "звід оператора", "author-recorded": "запис автора", "review-recorded": "зафіксоване рев’ю"}[s.Role]
				ref = s.Label + " · " + role + " · " + s.RecordedAt.UTC().Format("2006-01-02")
				break
			}
		}
		out.Stages[i] = stage{v.Name, v.State, v.Detail, ref}
	}
	out.Provenance = "Локальний запис, внесений видавцем дашборда. Збіг HEAD не підтверджує стан незакомічених змін."
	return out
}

// readOne is a project's card with its open-task queue, which is not bound to the revision.
func (r roots) readOne(id string, now time.Time) (project, feedRecord) {
	card, report := r.readStatus(id, now)
	card.Queue = r.readQueue(id, now)
	return card, report
}

func (r roots) readStatus(id string, now time.Time) (project, feedRecord) {
	head := revision(r.repo(id))
	out := base(id, projects.name(id), "Поточну задачу не підтверджено", head)
	out.Workflow = projects.byID[id].Workflow
	statusRaw, statusErr := fileFromFeed(r.feed, id)
	transitionRaw, transitionErr := feedFile(r.feed, id, kindTransition)
	f, ferr := decodeRecord(statusRaw)
	content := statusErr == nil && ferr == nil && f.validateContent(id) == nil
	reason := staleFuture
	if content {
		reason, _ = f.validateFresh(head, now)
	}
	usable := content && reason == freshOK
	if revision(r.repo(id)) != head {
		return out, feedRecord{}
	}
	if !missing(transitionErr) {
		t, err := decodeBounded[transitionRecord](transitionRaw, maxFeed, canonicalField)
		if transitionErr != nil || err != nil || t.validate(id, head, now) != nil {
			out.Next = "Запис переходу застарів або недійсний. Поточні гейти не підтверджено."
			return out, feedRecord{}
		}
		if !usable || !t.applicable(f) {
			out.Task = "Задача " + t.TaskID
			out.Transition = t.display(false)
			out.Next = "Перехід зафіксовано окремо. Попередні гейти збережено, але їх застосовність до цього зрізу не підтверджено."
			return out, feedRecord{}
		}
		card := f.card(head, digestBytes(statusRaw))
		card.Workflow = out.Workflow
		card.Transition = t.display(true)
		return card, f
	}
	if content && f.Schema == feedSchema && (reason == staleRevision || reason == staleAge) {
		return f.staleCard(head, reason, out.Workflow), feedRecord{}
	}
	if !usable || f.Schema != feedSchema {
		return out, feedRecord{}
	}
	card := f.card(head, digestBytes(statusRaw))
	card.Workflow = out.Workflow
	card.Provenance += " Це збережений запис без прив’язки до поточного переходу."
	return card, f
}

func missing(err error) bool { return os.IsNotExist(err) }

// feedKind names one of a project's feed files; each kind has its own file name and size bound.
type feedKind int

const (
	kindStatus feedKind = iota
	kindTransition
	kindQueue
)

func (k feedKind) limit() int {
	if k == kindQueue {
		return maxQueue
	}
	return maxFeed
}

func fileFromFeed(dir, id string) ([]byte, error) { return feedFile(dir, id, kindStatus) }
func feedName(id string, kind feedKind) string {
	switch kind {
	case kindTransition:
		return id + ".transition.json"
	case kindQueue:
		return id + ".queue.json"
	}
	return id + ".json"
}
func feedFile(dir, id string, kind feedKind) ([]byte, error) {
	if projects.name(id) == "" {
		return nil, errors.New("unknown project")
	}
	root, err := os.OpenRoot(dir)
	if err != nil {
		return nil, err
	}
	defer root.Close()
	f, info, err := boundedFile(root, feedName(id, kind), int64(kind.limit()))
	if err != nil {
		return nil, err
	}
	defer f.Close()
	raw, err := io.ReadAll(io.LimitReader(f, int64(kind.limit())+1))
	if err != nil || int64(len(raw)) != info.Size() {
		return nil, errors.New("status changed during read")
	}
	return raw, nil
}
func (r roots) publish(input io.Reader, apply bool, now time.Time) error {
	raw, err := io.ReadAll(io.LimitReader(input, maxFeed+1))
	if err != nil {
		return errors.New("could not read input")
	}
	p, err := decodeRecord(raw)
	if err != nil {
		return err
	}
	id := p.Project
	if projects.name(id) == "" {
		return errors.New("unknown project")
	}
	return r.publishFile(raw, id, kindStatus, apply, func() error {
		if err := p.validate(id, revision(r.repo(id)), now); err != nil {
			return err
		}
		old, err := fileFromFeed(r.feed, id)
		if err == nil {
			previous, err := decodeRecord(old)
			if err != nil || previous.Project != id {
				return errors.New("existing record is invalid; inspect manually")
			}
			if !p.UpdatedAt.After(previous.UpdatedAt) {
				return errors.New("new observation must be later than existing record")
			}
		} else if !os.IsNotExist(err) {
			return errors.New("existing record cannot be trusted")
		}
		return nil
	})
}

func (r roots) publishFile(raw []byte, id string, kind feedKind, apply bool, recheck func() error) error {
	if err := recheck(); err != nil {
		return err
	}
	if !apply {
		return nil
	}
	fi, err := os.Lstat(r.feed)
	if err != nil || !fi.IsDir() || fi.Mode().Perm()&077 != 0 {
		return errors.New("feed directory must exist and be private")
	}
	lock, err := os.OpenFile(filepath.Join(r.feed, ".publish.lock"), os.O_CREATE|os.O_RDWR|syscall.O_NOFOLLOW|syscall.O_NONBLOCK, 0600)
	if err != nil {
		return err
	}
	defer lock.Close()
	li, err := lock.Stat()
	if err != nil || !li.Mode().IsRegular() {
		return errors.New("invalid publish lock")
	}
	if err := syscall.Flock(int(lock.Fd()), syscall.LOCK_EX|syscall.LOCK_NB); err != nil {
		return errors.New("another publish is in progress")
	}
	tmp, err := os.CreateTemp(r.feed, ".pending-")
	if err != nil {
		return err
	}
	defer os.Remove(tmp.Name())
	if _, err := tmp.Write(raw); err != nil {
		tmp.Close()
		return err
	}
	if err := tmp.Sync(); err != nil {
		tmp.Close()
		return err
	}
	if err := tmp.Close(); err != nil {
		return err
	}
	if err := recheck(); err != nil {
		return err
	}
	if err := os.Rename(tmp.Name(), filepath.Join(r.feed, feedName(id, kind))); err != nil {
		return err
	}
	// Best effort: the record is already in place, and a reported failure would make the retry refuse its timestamp.
	if dir, err := os.Open(r.feed); err == nil {
		_ = dir.Sync()
		dir.Close()
	}
	return nil
}
