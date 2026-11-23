package main

import (
	"context"
	"net/http/httptest"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"testing"
)

func TestLocalListenerRefusesProxiedRequests(t *testing.T) {
	const local = "127.0.0.1:8732"
	h := dashboard(local, func(context.Context) snapshot { return snapshot{} }, nil)
	plain := httptest.NewRecorder()
	h.ServeHTTP(plain, httptest.NewRequest("GET", "http://"+local+"/api/status", nil))
	if plain.Code != 200 {
		t.Fatalf("plain local request: %d", plain.Code)
	}
	for _, header := range []string{"Forwarded", "Via", "X-Forwarded-For", "X-Forwarded-Host", "X-Forwarded-Proto",
		"X-Forwarded-Port", "X-Forwarded-Server", "X-Forwarded-Ssl", "X-Real-IP", "CF-Connecting-IP", "True-Client-IP"} {
		r := httptest.NewRequest("GET", "http://"+local+"/api/status", nil)
		r.Header.Set(header, "203.0.113.7")
		w := httptest.NewRecorder()
		h.ServeHTTP(w, r)
		if w.Code != 403 || strings.Contains(w.Body.String(), "projects") {
			t.Errorf("%s: %d", header, w.Code)
		}
	}
}

func writeAccounts(t *testing.T) string {
	t.Helper()
	path := filepath.Join(t.TempDir(), "share.accounts")
	if err := os.WriteFile(path, []byte("owner full "+strings.Repeat("ab", 32)+"\n"), 0600); err != nil {
		t.Fatal(err)
	}
	return path
}

func TestShareHandlerChoice(t *testing.T) {
	useProjects(t, projectConfig{ID: "project-a", Name: "Project A", Root: t.TempDir()})
	sources := roots{feed: t.TempDir()}
	const host, domain = "dash.share.example.test", "share.example.test"
	base := shareOptions{host: host, domain: domain, port: 8734}
	for name, o := range map[string]shareOptions{
		"local dashboard port":  {host: host, domain: domain, port: 8732},
		"host not under domain": {host: "dash.other.example.test", domain: domain, port: 8734},
		"publishing":            {host: host, domain: domain, port: 8734, publishing: true},
		"probe":                 {host: host, domain: domain, port: 8734, probe: true},
		"bad accounts file":     {host: host, domain: domain, port: 8734, auth: true, digest: filepath.Join(t.TempDir(), "missing")},
	} {
		if _, err := shareHandlerFor(o, sources); err == nil {
			t.Errorf("%s accepted", name)
		}
	}
	serve := func(o shareOptions, path string) int {
		h, err := shareHandlerFor(o, sources)
		if err != nil {
			t.Fatal(err)
		}
		r := httptest.NewRequest("GET", "http://"+host+path, nil)
		w := httptest.NewRecorder()
		h.ServeHTTP(w, r)
		return w.Code
	}
	withDigest := base
	withDigest.digest = writeAccounts(t)
	for _, path := range []string{"/", "/api/status", "/api/details/project-a"} {
		if code := serve(base, path); code != 403 {
			t.Errorf("share without auth %s: %d", path, code)
		}
		if code := serve(withDigest, path); code != 403 {
			t.Errorf("digest without -share-auth %s: %d", path, code)
		}
	}
	withAuth := withDigest
	withAuth.auth = true
	if code := serve(withAuth, "/api/status"); code != 401 {
		t.Errorf("auth without login: %d", code)
	}
}

func TestDockerLocalNamesAMissingDigest(t *testing.T) {
	sh, err := exec.LookPath("sh")
	if err != nil {
		t.Skip("no sh")
	}
	dir := t.TempDir()
	bin := filepath.Join(dir, "bin")
	if err := os.Mkdir(bin, 0700); err != nil {
		t.Fatal(err)
	}
	for _, tool := range []string{"go", "docker"} {
		if err := os.WriteFile(filepath.Join(bin, tool), []byte("#!/bin/sh\nexit 0\n"), 0700); err != nil {
			t.Fatal(err)
		}
	}
	projectsFile := filepath.Join(dir, "projects.json")
	feed := filepath.Join(dir, "feed")
	if err := os.WriteFile(projectsFile, []byte("[]"), 0600); err != nil {
		t.Fatal(err)
	}
	if err := os.Mkdir(feed, 0700); err != nil {
		t.Fatal(err)
	}
	cmd := exec.Command(sh, "docker-local.sh", "share", "sha256:"+strings.Repeat("a", 64))
	cmd.Env = []string{"PATH=" + bin + ":/usr/bin:/bin", "DASHBOARD_PROJECTS=" + projectsFile, "DASHBOARD_FEED=" + feed,
		"DASHBOARD_SHARE_HOST=dash.share.example.test", "DASHBOARD_SHARE_DOMAIN=share.example.test",
		"DASHBOARD_SHARE_AUTH=on", "DASHBOARD_SHARE_DIGEST=" + filepath.Join(dir, "absent.accounts")}
	out, err := cmd.CombinedOutput()
	exit, ok := err.(*exec.ExitError)
	if !ok || exit.ExitCode() != 2 || !strings.Contains(string(out), "share accounts file is missing") {
		t.Fatalf("exit %v: %s", err, out)
	}
}
