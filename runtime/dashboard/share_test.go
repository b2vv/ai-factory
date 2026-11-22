package main

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"net/http/httptest"
	"os"
	"path/filepath"
	"reflect"
	"strings"
	"testing"
	"time"
)

// appMarker is the bundle content the owner must receive: React in the default build,
// the fixed stub under -tags nobundle (the real bundle is then checked by the default build only).
var appMarker = map[bool]string{true: "react", false: "nobundle test stub"}[bundled]

func TestSharedDashboardBoundary(t *testing.T) {
	const host = "dash.share.example.test"
	useProjects(t, projectConfig{ID: "project-a", Name: "Project A", Root: "/srv/project-a"}, projectConfig{ID: "project-b", Name: "Project B", Root: "/srv/project-b"})
	password := strings.Repeat("a", 64) // fixture only
	calls := 0
	ownerPassword := strings.Repeat("c", 64)
	accounts := map[string]shareAccount{
		"owner":      {digest: sha256.Sum256([]byte(ownerPassword)), access: shareFull},
		"colleagues": {digest: sha256.Sum256([]byte(password)), access: shareStatus},
	}
	read := func() snapshot {
		calls++
		return snapshot{CheckedAt: time.Unix(0, 0).UTC(), Projects: []project{
			{ID: "project-a", Name: "PRIVATE_NAME", State: "Recorded", Revision: "PRIVATE_REVISION",
				Task: "PRIVATE_TASK", Next: "PRIVATE_NEXT", DetailID: "PRIVATE_DETAIL", DetailToken: "PRIVATE_TOKEN",
				Observed: "PRIVATE_TIME", Provenance: "PRIVATE_PROVENANCE", Workflow: "PRIVATE_WORKFLOW",
				Stages: []stage{{Name: "PRIVATE_STAGE", State: "PRIVATE_STAGE_STATE", Source: "PRIVATE_SOURCE"}}},
			{ID: "project-b", State: "PRIVATE_STATE"},
			{ID: "unexpected", State: "Recorded", Name: "PRIVATE_PROJECT"},
		}}
	}
	owner := dashboardAtOrigin(host, "https://"+host, func(_ context.Context) snapshot { return read() }, func(id string) (project, feedRecord) {
		return project{DetailToken: "PRIVATE_TOKEN"}, feedRecord{Markdown: "PRIVATE_MARKDOWN"}
	})
	handler := sharedDashboard(host, accounts, owner, read)

	for _, tc := range []struct {
		method, path, authority, auth, origin, fetchSite string
		duplicate                                        string
		want                                             int
	}{
		{"GET", "/", host, "", "", "", "", 401},
		{"GET", "/api/status", host, "", "", "", "", 401},
		{"GET", "/style.css", host, "", "", "", "", 401},
		{"GET", "/api/details/project-a", host, "", "", "", "", 401},
		{"GET", "/", host, "wrong-user", "", "", "", 401},
		{"GET", "/", host, strings.Repeat("b", 64), "", "", "", 401},
		{"GET", "/api/details/project-a", host, "colleague-as-owner", "", "", "", 401},
		{"GET", "/api/status", host, ownerPassword, "", "", "", 401},
		{"GET", "/", host, password, "", "", "Authorization", 401},
		{"GET", "/", "localhost:8734", password, "", "", "", 403},
		{"GET", "/", "127.0.0.1:8734", password, "", "", "", 403},
		{"GET", "/", "other.share.example.test", password, "", "", "", 403},
		{"GET", "/", host, password, "http://" + host, "", "", 403},
		{"GET", "/", host, password, "null", "", "", 403},
		{"GET", "/", host, password, "https://" + host, "", "Origin", 403},
		{"GET", "/api/status", host, password, "", "cross-site", "", 403},
		{"POST", "/api/status", host, password, "", "", "", 405},
		{"GET", "/api/details/project-a", host, password, "", "", "", 404},
		{"GET", "/app.js", host, password, "", "", "", 404},
		{"GET", "/api/status?extra=yes", host, password, "", "", "", 404},
		{"GET", "/api/status?", host, password, "", "", "", 404},
		{"GET", "/api/%73tatus", host, password, "", "", "", 404},
		{"GET", "/", host, password, "", "cross-site", "", 200},
		{"GET", "/style.css", host, password, "", "", "", 200},
		{"GET", "/api/status", host, password, "https://" + host, "same-origin", "", 200},
	} {
		t.Run(tc.method+" "+tc.path+" "+tc.authority, func(t *testing.T) {
			req := httptest.NewRequest(tc.method, "http://"+tc.authority+tc.path, nil)
			req.RemoteAddr = "127.0.0.1:54321"
			req.Header.Set("X-Forwarded-Host", host)
			req.Header.Set("X-Forwarded-For", "127.0.0.1")
			req.Header.Set("X-Forwarded-Proto", "https")
			if tc.auth != "" {
				if tc.auth == "wrong-user" {
					req.SetBasicAuth("other", password)
				} else if tc.auth == "colleague-as-owner" {
					req.SetBasicAuth("owner", password)
				} else {
					req.SetBasicAuth("colleagues", tc.auth)
				}
			}
			if tc.origin != "" {
				req.Header.Set("Origin", tc.origin)
			}
			if tc.duplicate != "" {
				req.Header.Add(tc.duplicate, req.Header.Get(tc.duplicate))
			}
			if tc.fetchSite != "" {
				req.Header.Set("Sec-Fetch-Site", tc.fetchSite)
				req.Header.Set("Sec-Fetch-Mode", "navigate")
				req.Header.Set("Sec-Fetch-Dest", "document")
			}
			w := httptest.NewRecorder()
			before := calls
			handler.ServeHTTP(w, req)
			if w.Code != tc.want {
				t.Fatalf("status %d, want %d: %s", w.Code, tc.want, w.Body)
			}
			if w.Header().Get("Cache-Control") != "no-store" || w.Header().Get("Access-Control-Allow-Origin") != "" ||
				!strings.Contains(w.Header().Get("Content-Security-Policy"), "frame-ancestors 'none'") {
				t.Fatal("missing response safety headers")
			}
			if w.Code == 401 && !strings.HasPrefix(w.Header().Get("WWW-Authenticate"), "Basic ") {
				t.Fatal("missing login challenge")
			}
			if (w.Code != 200 || tc.path == "/style.css") && calls != before {
				t.Fatal("the status feed was read from a denied or static request")
			}
			body := w.Body.String()
			if strings.Contains(body, "PRIVATE_") || strings.Contains(body, "react") {
				t.Fatal("internal content escaped the status-only boundary")
			}
			if w.Code != 200 {
				return
			}
			if tc.path == "/" && (!strings.Contains(body, "</html>") || !strings.Contains(body, "Recorded")) {
				t.Fatal("authenticated HTML did not render the statuses")
			}
			if tc.path == "/api/status" {
				var payload map[string]json.RawMessage
				if json.Unmarshal(w.Body.Bytes(), &payload) != nil || len(payload) != 2 || payload["checkedAt"] == nil {
					t.Fatal("unexpected JSON envelope")
				}
				var cards []map[string]string
				if json.Unmarshal(payload["projects"], &cards) != nil || len(cards) != len(projects.ids) {
					t.Fatal("unexpected project list")
				}
				for i, id := range projects.ids {
					state := "Unknown"
					if id == "project-a" {
						state = "Recorded"
					}
					if !reflect.DeepEqual(cards[i], map[string]string{"name": projects.name(id), "state": state}) {
						t.Fatalf("unexpected fields for %s: %#v", id, cards[i])
					}
				}
			}
		})
	}
	for _, route := range []struct{ path, marker string }{
		{"/", "/app.js"}, {"/app.js", appMarker}, {"/api/status", "PRIVATE_REVISION"}, {"/api/details/project-a", "PRIVATE_MARKDOWN"},
	} {
		req := httptest.NewRequest("GET", "http://"+host+route.path, nil)
		req.Header.Set("Origin", "https://"+host)
		req.SetBasicAuth("owner", ownerPassword)
		w := httptest.NewRecorder()
		handler.ServeHTTP(w, req)
		if w.Code != 200 || !strings.Contains(w.Body.String(), route.marker) ||
			w.Header().Get("Cache-Control") != "no-store" || w.Header().Get("Vary") != "Authorization" {
			t.Fatalf("owner did not receive local-equivalent route %s (status %d)", route.path, w.Code)
		}
		if route.path == "/api/details/project-a" && w.Header().Get("X-Dashboard-Detail-Token") != "PRIVATE_TOKEN" {
			t.Fatal("owner detail token missing")
		}
	}
}

func TestShareConfigInput(t *testing.T) {
	const domain = "share.example.test"
	for _, invalid := range []string{"", "localhost", domain, ".share.example.test", "*.share.example.test", "an.dash.share.example.test",
		"a.share.example.test:443", "https://a.share.example.test", "a.share.example.test.", "-a.share.example.test", "a-.share.example.test",
		"a.other.example.test", "A.share.example.test", "a.share.example.test/x"} {
		if validShareHost(invalid, domain) {
			t.Fatalf("accepted invalid host %q", invalid)
		}
	}
	if !validShareHost("dash-01.share.example.test", domain) {
		t.Fatal("rejected exact share hostname")
	}
	for _, invalid := range []string{"", "test", "localhost", "*.example.test", "Example.test", "example..test", ".example.test",
		"example.test.", "https://example.test", "example.test:443", "-x.example.test", strings.Repeat("a.", 101) + "test"} {
		if validShareHost("a."+invalid, invalid) {
			t.Fatalf("accepted invalid share domain %q", invalid)
		}
	}
	dir := t.TempDir()
	path := filepath.Join(dir, "digest")
	digests := [3][sha256.Size]byte{
		sha256.Sum256([]byte("fixture-owner")), sha256.Sum256([]byte("fixture-colleague1")), sha256.Sum256([]byte("fixture-colleague2")),
	}
	ownerHex, firstHex, secondHex := hex.EncodeToString(digests[0][:]), hex.EncodeToString(digests[1][:]), hex.EncodeToString(digests[2][:])
	valid := "alice full " + ownerHex + "\nbob@example.test status " + firstHex + "\ncarol status " + secondHex + "\n"
	if err := os.WriteFile(path, []byte(valid), 0600); err != nil {
		t.Fatal(err)
	}
	want := map[string]shareAccount{"alice": {digests[0], shareFull}, "bob@example.test": {digests[1], shareStatus}, "carol": {digests[2], shareStatus}}
	if got, err := loadShareAccounts(path); err != nil || !reflect.DeepEqual(got, want) {
		t.Fatalf("valid accounts failed: %v", err)
	}
	for _, tc := range []struct {
		raw  string
		mode os.FileMode
	}{
		{valid, 0644}, {"", 0600}, {"not a digest", 0600}, {" " + valid, 0600}, {valid + "\n", 0600},
		{"alice admin " + ownerHex + "\n", 0600}, {"alice full " + ownerHex + "\nalice status " + firstHex + "\n", 0600},
		{"alice full " + ownerHex + "\nbob status " + ownerHex + "\n", 0600},
		{"alice full " + strings.Repeat("0", 64) + "\n", 0600}, {"alice:test status " + firstHex + "\n", 0600},
	} {
		if err := os.WriteFile(path, []byte(tc.raw), 0600); err != nil {
			t.Fatal(err)
		}
		if err := os.Chmod(path, tc.mode); err != nil {
			t.Fatal(err)
		}
		if _, err := loadShareAccounts(path); err == nil {
			t.Fatal("accepted unsafe or invalid account file")
		}
	}

	link := filepath.Join(dir, "link")
	if err := os.Symlink(path, link); err != nil {
		t.Fatal(err)
	}
	for _, invalid := range []string{link, dir, filepath.Join(dir, "missing")} {
		if _, err := loadShareAccounts(invalid); err == nil {
			t.Fatal("accepted non-regular or missing digest")
		}
	}
}

func TestShareDisabled(t *testing.T) {
	for _, method := range []string{"GET", "POST", "OPTIONS"} {
		for _, path := range []string{"/", "/api/status", "/api/details/project-a", "/style.css", "/app.js"} {
			w := httptest.NewRecorder()
			r := httptest.NewRequest(method, "http://dash.share.example.test"+path, nil)
			r.SetBasicAuth("owner", strings.Repeat("a", 64))
			shareForbidden(w, r)
			if w.Code != 403 || w.Header().Get("WWW-Authenticate") != "" || w.Header().Get("Cache-Control") != "no-store" {
				t.Fatalf("disabled mode is not closed on %s %s", method, path)
			}
		}
	}
}

func TestShareTunnelHost(t *testing.T) {
	const host = "dash.share.example.test"
	useProjects(t, projectConfig{ID: "project-a", Name: "Project A", Root: "/srv/project-a"})
	password := strings.Repeat("b", 64) // fixture only
	accounts := map[string]shareAccount{"colleague": {digest: sha256.Sum256([]byte(password)), access: shareStatus}}
	read := func() snapshot { return snapshot{CheckedAt: time.Unix(0, 0)} }
	handler := shareTunnelHost(host, 8734, sharedDashboard(host, accounts, nil, read))
	cases := []struct {
		name, authority string
		forwarded       map[string][]string
		login           bool
		want            int
	}{
		{"tunnel without login asks for it", "localhost:8734", map[string][]string{"X-Forwarded-Host": {host}, "X-Forwarded-Proto": {"https"}}, false, 401},
		{"tunnel with login", "localhost:8734", map[string][]string{"X-Forwarded-Host": {host}, "X-Forwarded-Proto": {"https"}}, true, 200},
		{"loopback ip tunnel", "127.0.0.1:8734", map[string][]string{"X-Forwarded-Host": {host}, "X-Forwarded-Proto": {"https"}}, true, 200},
		{"exact host still works", host, nil, true, 200},
		{"other forwarded host", "localhost:8734", map[string][]string{"X-Forwarded-Host": {"evil.example.test"}, "X-Forwarded-Proto": {"https"}}, true, 403},
		{"plain http forwarded", "localhost:8734", map[string][]string{"X-Forwarded-Host": {host}, "X-Forwarded-Proto": {"http"}}, true, 403},
		{"no proto", "localhost:8734", map[string][]string{"X-Forwarded-Host": {host}}, true, 403},
		{"two forwarded hosts", "localhost:8734", map[string][]string{"X-Forwarded-Host": {host, host}, "X-Forwarded-Proto": {"https"}}, true, 403},
		{"other local port", "localhost:8732", map[string][]string{"X-Forwarded-Host": {host}, "X-Forwarded-Proto": {"https"}}, true, 403},
		{"foreign authority with forwarded host", "evil.example.test", map[string][]string{"X-Forwarded-Host": {host}, "X-Forwarded-Proto": {"https"}}, true, 403},
		{"loopback without forwarding", "localhost:8734", nil, true, 403},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			req := httptest.NewRequest("GET", "http://"+tc.authority+"/api/status", nil)
			for k, vs := range tc.forwarded {
				for _, v := range vs {
					req.Header.Add(k, v)
				}
			}
			if tc.login {
				req.SetBasicAuth("colleague", password)
			}
			rec := httptest.NewRecorder()
			handler.ServeHTTP(rec, req)
			if rec.Code != tc.want {
				t.Fatalf("got %d, want %d", rec.Code, tc.want)
			}
		})
	}
}

func TestSharePasswordsAndAttemptLimit(t *testing.T) {
	const host = "dash.share.example.test"
	useProjects(t, projectConfig{ID: "project-a", Name: "Project A", Root: "/srv/project-a"})
	short, tooShort := "Test-pw8", "Test-p7" // fixtures only
	accounts := map[string]shareAccount{"colleague": {digest: sha256.Sum256([]byte(short)), access: shareStatus},
		"seven": {digest: sha256.Sum256([]byte(tooShort)), access: shareStatus}}
	now := time.Unix(1000, 0)
	shareNow = func() time.Time { return now }
	t.Cleanup(func() { shareNow = time.Now })
	read := func() snapshot { return snapshot{CheckedAt: time.Unix(0, 0)} }
	handler := sharedDashboard(host, accounts, nil, read)
	get := func(user, password string) int {
		req := httptest.NewRequest("GET", "http://"+host+"/api/status", nil)
		if user != "" {
			req.SetBasicAuth(user, password)
		}
		rec := httptest.NewRecorder()
		handler.ServeHTTP(rec, req)
		return rec.Code
	}
	if c := get("colleague", short); c != 200 {
		t.Fatalf("8-character password: got %d", c)
	}
	if c := get("seven", tooShort); c != 401 {
		t.Fatalf("7-character password must be refused even with a matching digest: got %d", c)
	}
	for i := 1; i < shareFailureLimit; i++ {
		if c := get("colleague", "wrong-password"); c != 401 {
			t.Fatalf("wrong attempt %d: got %d", i, c)
		}
	}
	if c := get("", ""); c != 401 {
		t.Fatalf("a request without credentials is a login challenge, not an attempt: got %d", c)
	}
	if c := get("colleague", short); c != 429 {
		t.Fatalf("after %d wrong attempts even the right password waits: got %d", shareFailureLimit, c)
	}
	now = now.Add(shareFailureWindow)
	if c := get("colleague", short); c != 200 {
		t.Fatalf("after the window the right password works again: got %d", c)
	}
}
