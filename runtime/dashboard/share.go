package main

import (
	"crypto/sha256"
	"crypto/subtle"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"html/template"
	"io"
	"io/fs"
	"net/http"
	"os"
	"path/filepath"
	"regexp"
	"strings"
	"sync"
	"time"
)

const dnsLabel = `[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?`

// The share domain is deployment configuration (required when sharing is on).
// It needs at least two labels; the host is exactly one more label under it.
var shareDomainPattern = regexp.MustCompile(`^` + dnsLabel + `(?:\.` + dnsLabel + `)+$`)
var shareLabelPattern = regexp.MustCompile(`^` + dnsLabel + `$`)

// shareSuffixPattern is what one '*' in a share host stands for: the random suffix a
// share provider appends when it assigns a new link name (for example after a restart).
var shareSuffixPattern = regexp.MustCompile(`^[a-z0-9]{1,32}$`)

// validShareHost accepts an exact host one label under domain, or that label ending in
// one '*' after a non-empty prefix (dash-*.share.example.test).
func validShareHost(host, domain string) bool {
	if len(domain) > 200 || !shareDomainPattern.MatchString(domain) {
		return false
	}
	label, rest, ok := strings.Cut(host, ".")
	if !ok || rest != domain {
		return false
	}
	if prefix, found := strings.CutSuffix(label, "*"); found {
		return prefix != "" && shareLabelPattern.MatchString(prefix+"0")
	}
	return shareLabelPattern.MatchString(label)
}

// shareHostMatches reports whether name is the configured share host: equal to it, or,
// for a host with '*', the same name with one random suffix in place of the '*'.
func shareHostMatches(host, name string) bool {
	prefix, rest, found := strings.Cut(host, "*")
	if !found {
		return name == host
	}
	tail, ok := strings.CutPrefix(name, prefix)
	if !ok {
		return false
	}
	suffix, domain, ok := strings.Cut(tail, ".")
	return ok && "."+domain == rest && shareSuffixPattern.MatchString(suffix) && shareLabelPattern.MatchString(prefix+suffix)
}

var shareTokenPattern = regexp.MustCompile(`^[a-f0-9]{64}$`)

// sharePasswordPattern accepts any printable ASCII password of 8..256 characters.
// Wrong attempts are rate-limited per listener (shareFailureLimit per shareFailureWindow).
var sharePasswordPattern = regexp.MustCompile(`^[\x21-\x7e]{8,256}$`)

const shareFailureLimit = 20
const shareFailureWindow = time.Minute

// shareFailures counts presented-but-wrong logins in a sliding window, for the whole listener.
type shareFailures struct {
	mu    sync.Mutex
	times []time.Time
}

func (f *shareFailures) blocked(now time.Time) bool {
	f.mu.Lock()
	defer f.mu.Unlock()
	kept := f.times[:0]
	for _, t := range f.times {
		if now.Sub(t) < shareFailureWindow {
			kept = append(kept, t)
		}
	}
	f.times = kept
	return len(f.times) >= shareFailureLimit
}

func (f *shareFailures) add(now time.Time) {
	f.mu.Lock()
	defer f.mu.Unlock()
	f.times = append(f.times, now)
}

type shareAccess uint8

const (
	shareDenied shareAccess = iota
	shareStatus
	shareFull
)

type shareAccount struct {
	digest [sha256.Size]byte
	access shareAccess
}

var shareLoginPattern = regexp.MustCompile(`^[A-Za-z0-9][A-Za-z0-9_.@-]{0,63}$`)

func loadShareAccounts(path string) (map[string]shareAccount, error) {
	dir, err := os.OpenRoot(filepath.Dir(path))
	if err != nil {
		return nil, err
	}
	defer dir.Close()
	const maxAccounts = 32
	const maxSize = 4608
	f, info, err := boundedFile(dir, filepath.Base(path), maxSize)
	if err != nil {
		return nil, err
	}
	defer f.Close()
	if info.Mode().Perm() != 0600 {
		return nil, errors.New("expected a mode-0600 credentials file")
	}
	raw, err := io.ReadAll(io.LimitReader(f, maxSize+1))
	if err != nil || int64(len(raw)) != info.Size() {
		return nil, errors.New("could not read share accounts")
	}
	accounts := make(map[string]shareAccount)
	seen := make(map[[sha256.Size]byte]bool)
	for line := range strings.SplitSeq(strings.TrimSuffix(string(raw), "\n"), "\n") {
		parts := strings.Split(line, " ")
		if len(parts) != 3 || !shareLoginPattern.MatchString(parts[0]) || !shareTokenPattern.MatchString(parts[2]) {
			return nil, errors.New("expected login role password-digest per line")
		}
		account := shareAccount{}
		switch parts[1] {
		case "status":
			account.access = shareStatus
		case "full":
			account.access = shareFull
		default:
			return nil, errors.New("expected a status or full role")
		}
		_, _ = hex.Decode(account.digest[:], []byte(parts[2]))
		if accounts[parts[0]].access != shareDenied || seen[account.digest] ||
			account.digest == ([sha256.Size]byte{}) || len(accounts) == maxAccounts {
			return nil, errors.New("invalid or duplicate share account")
		}
		accounts[parts[0]] = account
		seen[account.digest] = true
	}
	return accounts, nil
}

func shareForbidden(w http.ResponseWriter, _ *http.Request) {
	dashboardHeaders(w)
	http.Error(w, "Forbidden", http.StatusForbidden)
}

type sharedProject struct {
	Name  string `json:"name"`
	State string `json:"state"`
}

type sharedSnapshot struct {
	CheckedAt time.Time       `json:"checkedAt"`
	Projects  []sharedProject `json:"projects"`
}

// projectStates deliberately selects two fields. Never marshal or render an
// internal project in the status-only view.
func projectStates(s snapshot) sharedSnapshot {
	out := sharedSnapshot{CheckedAt: s.CheckedAt}
	for _, id := range projects.ids {
		state := "Unknown"
		for _, p := range s.Projects {
			if p.ID != id {
				continue
			}
			switch p.State {
			case "Recorded", "Decision needed", "Verification pending", "Plan accepted", "Stale":
				state = p.State
			}
			break
		}
		out.Projects = append(out.Projects, sharedProject{projects.name(id), state})
	}
	return out
}

var sharedPage = template.Must(template.New("shared-dashboard").Parse(`<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>AI Factory project status</title><link rel="stylesheet" href="/style.css"></head>
<body><main class="shell">
<header class="mast"><span class="mark" aria-hidden="true">AF</span> AI Factory <span class="readonly">Read-only</span></header>
<div class="intro"><h1>Project status</h1><p>Refresh the page for the latest available statuses.</p></div>
<p class="freshness">Checked at <time datetime="{{.CheckedAt.Format "2006-01-02T15:04:05Z07:00"}}">{{.CheckedAt.UTC.Format "15:04 UTC"}}</time></p>
<div class="project-grid">{{range .Projects}}<section class="project-card"><h2>{{.Name}}</h2><p class="badge">{{.State}}</p></section>{{end}}</div>
</main></body></html>`))

// shareTunnelHost lets the share listener accept a request from a local share tunnel
// that rewrites the authority (Kiri Share, for one, sends Host: localhost:<port> and the public
// name in X-Forwarded-Host). Only this exact shape is mapped to the share host: the
// loopback authority of this listener, exactly one X-Forwarded-Host equal to the share
// host and exactly one X-Forwarded-Proto of https. Anything else is passed on unchanged,
// so the exact-host check below still refuses it. Login is still required.
// A host with '*' (shareHostMatches) maps every matching name, and an Origin of that
// same name, to the configured host; any other name is refused here.
// shareNow is the limiter's clock; tests replace it.
var shareNow = time.Now

func shareTunnelHost(host string, port int, next http.Handler) http.Handler {
	local := map[string]bool{fmt.Sprintf("localhost:%d", port): true, fmt.Sprintf("127.0.0.1:%d", port): true}
	pattern := strings.Contains(host, "*")
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		name := r.Host
		fh, fp := r.Header.Values("X-Forwarded-Host"), r.Header.Values("X-Forwarded-Proto")
		if local[r.Host] && len(fh) == 1 && len(fp) == 1 && fp[0] == "https" {
			name = fh[0]
		}
		if !shareHostMatches(host, name) {
			if pattern {
				shareForbidden(w, r)
				return
			}
			next.ServeHTTP(w, r)
			return
		}
		if name != r.Host || pattern {
			r = r.Clone(r.Context())
			r.Host = host
			if origins := r.Header.Values("Origin"); pattern && len(origins) == 1 && origins[0] == "https://"+name {
				r.Header.Set("Origin", "https://"+host)
			}
		}
		next.ServeHTTP(w, r)
	})
}

func sharedDashboard(host string, accounts map[string]shareAccount, owner http.Handler, read func() snapshot) http.Handler {
	failures := &shareFailures{}
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		dashboardHeaders(w)
		w.Header().Set("Vary", "Authorization")
		w.Header().Set("Content-Security-Policy", "default-src 'none'; style-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'")
		// Exact public authority is an additional restriction, not authentication.
		// The share proxy's source IP is not trusted; forwarded headers only through shareTunnelHost.
		origins := r.Header.Values("Origin")
		if r.Host != host || len(origins) > 1 || len(origins) == 1 && origins[0] != "https://"+host ||
			r.Header.Get("Sec-Fetch-Site") == "cross-site" && !dashboardNavigation(r) {
			http.Error(w, "Forbidden", http.StatusForbidden)
			return
		}
		user, password, ok := r.BasicAuth()
		if ok && failures.blocked(shareNow()) {
			w.Header().Set("Retry-After", "60")
			http.Error(w, "Too many attempts", http.StatusTooManyRequests)
			return
		}
		candidate := sha256.Sum256([]byte(password))
		account := accounts[user]
		match := subtle.ConstantTimeCompare(candidate[:], account.digest[:])
		if !ok || len(r.Header.Values("Authorization")) != 1 || !sharePasswordPattern.MatchString(password) || match != 1 || account.access == shareDenied {
			if ok {
				failures.add(shareNow())
			}
			w.Header().Set("WWW-Authenticate", `Basic realm="Factory dashboard"`)
			http.Error(w, "Authentication required", http.StatusUnauthorized)
			return
		}
		if r.Method != http.MethodGet {
			w.Header().Set("Allow", "GET")
			http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
			return
		}
		if r.URL.RawQuery != "" || r.URL.ForceQuery || r.URL.RawPath != "" {
			http.NotFound(w, r)
			return
		}
		if account.access == shareFull {
			owner.ServeHTTP(w, r)
			return
		}
		switch r.URL.Path {
		case "/":
			w.Header().Set("Content-Type", "text/html; charset=utf-8")
			_ = sharedPage.Execute(w, projectStates(read()))
		case "/api/status":
			w.Header().Set("Content-Type", "application/json")
			_ = json.NewEncoder(w).Encode(projectStates(read()))
		case "/style.css":
			data, err := fs.ReadFile(assets, "ui/style.css")
			if err != nil {
				http.Error(w, "Asset unavailable", http.StatusInternalServerError)
				return
			}
			w.Header().Set("Content-Type", "text/css; charset=utf-8")
			_, _ = w.Write(data)
		default:
			http.NotFound(w, r)
		}
	})
}
