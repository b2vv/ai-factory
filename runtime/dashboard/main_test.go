package main

import (
	"context"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestHTTPNarrowReadOnlyScope(t *testing.T) {
	const local = "127.0.0.1:8732"
	reads := 0
	h := dashboard(local, func(context.Context) snapshot { reads++; return snapshot{} }, nil)
	for _, tc := range []struct {
		method, url, origin, fetchSite string
		code                           int
	}{
		{"GET", "http://" + local + "/", "", "", 200},
		{"GET", "http://" + local + "/app.js", "", "", 200},
		{"GET", "http://" + local + "/style.css", "", "", 200},
		{"GET", "http://" + local + "/api/status", "", "same-origin", 200},
		{"POST", "http://" + local + "/api/status", "", "", 405},
		{"GET", "http://" + local + "/api/status?file=/etc/passwd", "", "", 404},
		{"GET", "http://" + local + "/main.go", "", "", 404},
		{"GET", "http://" + local + "/ui/dist/app.js", "", "", 404},
		{"GET", "http://web.invalid/api/status", "", "", 403},
		{"GET", "http://" + local + "/api/status", "http://web.invalid", "", 403},
		{"GET", "http://" + local + "/api/status", "", "cross-site", 403},
	} {
		r := httptest.NewRequest(tc.method, tc.url, nil)
		if tc.origin != "" {
			r.Header.Set("Origin", tc.origin)
		}
		if tc.fetchSite != "" {
			r.Header.Set("Sec-Fetch-Site", tc.fetchSite)
		}
		w := httptest.NewRecorder()
		h.ServeHTTP(w, r)
		if w.Code != tc.code {
			t.Errorf("%s %s returned %d want %d", tc.method, tc.url, w.Code, tc.code)
		}
		if w.Header().Get("Cache-Control") != "no-store" || w.Header().Get("Content-Security-Policy") == "" {
			t.Fatal("missing protective headers")
		}
	}
	for _, tc := range []struct {
		path, mode, dest string
		code             int
	}{
		{"/", "navigate", "document", 200},
		{"/", "navigate", "iframe", 403},
		{"/", "no-cors", "image", 403},
		{"/api/status", "navigate", "document", 403},
		{"/app.js", "no-cors", "script", 403},
	} {
		r := httptest.NewRequest("GET", "http://"+local+tc.path, nil)
		r.Header.Set("Sec-Fetch-Site", "cross-site")
		r.Header.Set("Sec-Fetch-Mode", tc.mode)
		r.Header.Set("Sec-Fetch-Dest", tc.dest)
		w := httptest.NewRecorder()
		h.ServeHTTP(w, r)
		if w.Code != tc.code {
			t.Errorf("cross-site %s to %s returned %d, want %d", tc.dest, tc.path, w.Code, tc.code)
		}
	}
	if reads != 1 {
		t.Fatalf("expected one snapshot read, got %d", reads)
	}
}

var _ http.Handler = dashboard("", nil, nil)

func TestGitMetadataReader(t *testing.T) {
	root := t.TempDir()
	git := filepath.Join(root, ".git")
	if err := os.MkdirAll(filepath.Join(git, "refs/heads"), 0700); err != nil {
		t.Fatal(err)
	}
	a := strings.Repeat("a", 40)
	b := strings.Repeat("b", 40)
	put := func(name, value string) {
		t.Helper()
		if err := os.WriteFile(filepath.Join(git, name), []byte(value), 0600); err != nil {
			t.Fatal(err)
		}
	}
	put("HEAD", "ref: refs/heads/main\n")
	put("packed-refs", "# pack-refs\n"+a+" refs/heads/main\n"+b+" refs/heads/main2\n")
	if got := revision(root); got != a {
		t.Fatalf("expected packed rev; got %q", got)
	}
	put("refs/heads/main", b+"\n")
	if got := revision(root); got != b {
		t.Fatalf("loose ref should supersede packed: %q", got)
	}
	put("refs/heads/main", "malformed\n")
	if got := revision(root); got != "" {
		t.Fatalf("malformed loose ref fell back to packed: %q", got)
	}
	put("HEAD", a+"\n")
	if got := revision(root); got != a {
		t.Fatalf("detached rev not observed: %q", got)
	}
	put("HEAD", "ref: refs/heads/../../escape\n")
	if got := revision(root); got != "" {
		t.Fatalf("unsafe ref parsed: %q", got)
	}
}
