package main

import (
	"bufio"
	"bytes"
	"encoding/json"
	"io"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"syscall"
	"testing"
	"time"
)

// TestProcessRestartDurability builds and runs the real factory binary (composition
// root + config + 0600 operator token-file startup), then proves a mutation survives a
// genuine process restart. This covers what httptest handler tests cannot: the binary
// starting, binding loopback, loading the durable state, and reloading it after exit.
func TestProcessRestartDurability(t *testing.T) {
	if testing.Short() {
		t.Skip("skipping process-level smoke in -short")
	}
	tmp := t.TempDir()
	bin := filepath.Join(tmp, "factory")
	build := exec.Command("go", "build", "-o", bin, ".")
	build.Dir = "."
	if out, err := build.CombinedOutput(); err != nil {
		t.Fatalf("go build: %v\n%s", err, out)
	}

	state := filepath.Join(tmp, "state")
	tokPath := filepath.Join(tmp, "operator.json")
	writeFile0600(t, tokPath, `{"id":"operator","secret":"smoke-secret"}`)

	// Explicit operator initialization (A): normal startup no longer auto-initializes.
	initState(t, bin, state)

	// First run: start, health, mint a project, stop.
	addr1, stop1 := start(t, bin, state, tokPath)
	if code, _ := httpGet(t, "http://"+addr1+"/health"); code != 200 {
		stop1()
		t.Fatalf("health on first run: %d", code)
	}
	if code := mint(t, addr1, "proj-smoke"); code != http.StatusCreated {
		stop1()
		t.Fatalf("first mint must be 201, got %d", code)
	}
	// Operator auth negative check at the process level.
	if code := mintNoAuth(t, addr1, "proj-x"); code != http.StatusUnauthorized {
		stop1()
		t.Fatalf("mint without operator secret must be 401, got %d", code)
	}
	stop1()

	// Second run against the SAME state dir: the project must already exist (durable).
	addr2, stop2 := start(t, bin, state, tokPath)
	defer stop2()
	if code, body := httpGet(t, "http://"+addr2+"/health"); code != 200 || body["registry_blocked"] != false {
		t.Fatalf("health on restart: code=%d body=%v", code, body)
	}
	if code := mint(t, addr2, "proj-smoke"); code == http.StatusCreated {
		t.Fatalf("re-minting the same project after restart must NOT succeed (durable state lost?), got 201")
	}
}

// TestProcessStartRequiresInitialization proves A at the process level: a normal start
// against an UNINITIALIZED (or mistyped) state dir does NOT silently create authority. The
// server starts so /health is observable but reports BLOCKED, and mutations are refused.
func TestProcessStartRequiresInitialization(t *testing.T) {
	if testing.Short() {
		t.Skip("skipping process-level smoke in -short")
	}
	tmp := t.TempDir()
	bin := buildFactory(t, tmp)
	state := filepath.Join(tmp, "uninit-state") // never initialized
	tokPath := filepath.Join(tmp, "operator.json")
	writeFile0600(t, tokPath, `{"id":"operator","secret":"smoke-secret"}`)

	addr, stop := start(t, bin, state, tokPath)
	defer stop()
	if code, body := httpGet(t, "http://"+addr+"/health"); code != 200 || body["registry_blocked"] != true {
		t.Fatalf("uninitialized start must report registry_blocked=true, got code=%d body=%v", code, body)
	}
	if code := mint(t, addr, "proj-x"); code != http.StatusServiceUnavailable {
		t.Fatalf("mint against an uninitialized (BLOCKED) registry must be 503, got %d", code)
	}
}

// TestCrossProcessExclusiveOwnership proves B with REAL subprocess contention: while one
// process owns the state dir, a second process on the SAME dir must refuse to start, and
// must not alter the durable state. After the owner exits, a third process reopens cleanly.
func TestCrossProcessExclusiveOwnership(t *testing.T) {
	if testing.Short() {
		t.Skip("skipping process-level smoke in -short")
	}
	tmp := t.TempDir()
	bin := buildFactory(t, tmp)
	state := filepath.Join(tmp, "state")
	tokPath := filepath.Join(tmp, "operator.json")
	writeFile0600(t, tokPath, `{"id":"operator","secret":"smoke-secret"}`)
	initState(t, bin, state)

	addr1, stop1 := start(t, bin, state, tokPath)
	if code := mint(t, addr1, "proj-owned"); code != http.StatusCreated {
		stop1()
		t.Fatalf("owner mint must be 201, got %d", code)
	}
	metaBefore := readFile(t, filepath.Join(state, "control.meta"))

	// Second process on the same state dir must fail to start (lock held by proc1).
	cmd2 := exec.Command(bin, "-state", state, "-operator-token", tokPath, "-listen", "127.0.0.1:0")
	out2, err2 := cmd2.CombinedOutput()
	if err2 == nil {
		stop1()
		t.Fatalf("second process on a locked state dir must fail to start; got success:\n%s", out2)
	}
	if !strings.Contains(string(out2), "owned by another running process") {
		stop1()
		t.Fatalf("second process must fail with an exclusive-ownership error, got:\n%s", out2)
	}
	// The rejected startup must not have changed authority state.
	if metaAfter := readFile(t, filepath.Join(state, "control.meta")); !bytes.Equal(metaBefore, metaAfter) {
		stop1()
		t.Fatalf("rejected startup altered control.meta:\nbefore=%s\nafter=%s", metaBefore, metaAfter)
	}
	stop1()

	// After the owner exits, a fresh process reopens cleanly and sees the durable project.
	addr3, stop3 := start(t, bin, state, tokPath)
	defer stop3()
	if code, body := httpGet(t, "http://"+addr3+"/health"); code != 200 || body["registry_blocked"] != false {
		t.Fatalf("reopen after owner exit must be healthy, got code=%d body=%v", code, body)
	}
	if code := mint(t, addr3, "proj-owned"); code == http.StatusCreated {
		t.Fatalf("project must still be durable after owner exit + reopen (re-mint should not be 201)")
	}
}

// TestReopenAfterAbruptTermination proves B's crash case: when the owner is SIGKILLed (no
// graceful release), the OS drops the flock, so a successor process reopens the same state
// dir and the previously-minted project is still durable.
func TestReopenAfterAbruptTermination(t *testing.T) {
	if testing.Short() {
		t.Skip("skipping process-level smoke in -short")
	}
	tmp := t.TempDir()
	bin := buildFactory(t, tmp)
	state := filepath.Join(tmp, "state")
	tokPath := filepath.Join(tmp, "operator.json")
	writeFile0600(t, tokPath, `{"id":"operator","secret":"smoke-secret"}`)
	initState(t, bin, state)

	cmd := exec.Command(bin, "-state", state, "-operator-token", tokPath, "-listen", "127.0.0.1:0")
	stdout, err := cmd.StdoutPipe()
	if err != nil {
		t.Fatal(err)
	}
	cmd.Stderr = &bytes.Buffer{}
	if err := cmd.Start(); err != nil {
		t.Fatal(err)
	}
	addr := awaitListen(t, stdout, cmd)
	if code := mint(t, addr, "proj-crash"); code != http.StatusCreated {
		cmd.Process.Kill()
		t.Fatalf("mint before crash must be 201, got %d", code)
	}
	// Abrupt termination: no graceful shutdown, no lock release in-process.
	if err := cmd.Process.Signal(syscall.SIGKILL); err != nil {
		t.Fatalf("SIGKILL: %v", err)
	}
	cmd.Wait()

	// Successor process must acquire the lock the OS released and see durable state.
	addr2, stop2 := start(t, bin, state, tokPath)
	defer stop2()
	if code, body := httpGet(t, "http://"+addr2+"/health"); code != 200 || body["registry_blocked"] != false {
		t.Fatalf("reopen after SIGKILL must be healthy, got code=%d body=%v", code, body)
	}
	if code := mint(t, addr2, "proj-crash"); code == http.StatusCreated {
		t.Fatalf("project minted before SIGKILL must still be durable after reopen (re-mint should not be 201)")
	}
}

func buildFactory(t *testing.T, tmp string) string {
	t.Helper()
	bin := filepath.Join(tmp, "factory")
	build := exec.Command("go", "build", "-o", bin, ".")
	build.Dir = "."
	if out, err := build.CombinedOutput(); err != nil {
		t.Fatalf("go build: %v\n%s", err, out)
	}
	return bin
}

func initState(t *testing.T, bin, state string) {
	t.Helper()
	out, err := exec.Command(bin, "-init", "-state", state).CombinedOutput()
	if err != nil {
		t.Fatalf("init: %v\n%s", err, out)
	}
	if !strings.Contains(string(out), "INITIALIZED") {
		t.Fatalf("init did not confirm initialization: %s", out)
	}
}

func readFile(t *testing.T, path string) []byte {
	t.Helper()
	b, err := os.ReadFile(path)
	if err != nil {
		t.Fatalf("read %s: %v", path, err)
	}
	return b
}

// awaitListen reads stdout until the LISTEN line and returns the bound address.
func awaitListen(t *testing.T, stdout io.Reader, cmd *exec.Cmd) string {
	t.Helper()
	addrCh := make(chan string, 1)
	go func() {
		sc := bufio.NewScanner(stdout)
		for sc.Scan() {
			if line := sc.Text(); strings.HasPrefix(line, "LISTEN ") {
				addrCh <- strings.TrimPrefix(line, "LISTEN ")
				io.Copy(io.Discard, stdout)
				return
			}
		}
		addrCh <- ""
	}()
	select {
	case addr := <-addrCh:
		if addr == "" {
			cmd.Process.Kill()
			t.Fatal("binary did not announce a listen address")
		}
		return addr
	case <-time.After(20 * time.Second):
		cmd.Process.Kill()
		t.Fatal("timed out waiting for LISTEN line")
		return ""
	}
}

func start(t *testing.T, bin, state, tok string) (string, func()) {
	t.Helper()
	cmd := exec.Command(bin, "-state", state, "-operator-token", tok, "-listen", "127.0.0.1:0")
	stdout, err := cmd.StdoutPipe()
	if err != nil {
		t.Fatal(err)
	}
	cmd.Stderr = &bytes.Buffer{}
	if err := cmd.Start(); err != nil {
		t.Fatal(err)
	}
	addrCh := make(chan string, 1)
	go func() {
		sc := bufio.NewScanner(stdout)
		for sc.Scan() {
			if line := sc.Text(); strings.HasPrefix(line, "LISTEN ") {
				addrCh <- strings.TrimPrefix(line, "LISTEN ")
				io.Copy(io.Discard, stdout) // drain the rest
				return
			}
		}
		addrCh <- ""
	}()
	var addr string
	select {
	case addr = <-addrCh:
	case <-time.After(20 * time.Second):
		cmd.Process.Kill()
		t.Fatal("timed out waiting for LISTEN line")
	}
	if addr == "" {
		cmd.Process.Kill()
		t.Fatal("binary did not announce a listen address")
	}
	stop := func() {
		_ = cmd.Process.Signal(syscall.SIGTERM)
		done := make(chan struct{})
		go func() { cmd.Wait(); close(done) }()
		select {
		case <-done:
		case <-time.After(10 * time.Second):
			cmd.Process.Kill()
		}
	}
	return addr, stop
}

func httpGet(t *testing.T, url string) (int, map[string]any) {
	t.Helper()
	var lastErr error
	for i := 0; i < 50; i++ {
		resp, err := http.Get(url)
		if err != nil {
			lastErr = err
			time.Sleep(50 * time.Millisecond)
			continue
		}
		defer resp.Body.Close()
		var m map[string]any
		_ = json.NewDecoder(resp.Body).Decode(&m)
		return resp.StatusCode, m
	}
	t.Fatalf("GET %s failed: %v", url, lastErr)
	return 0, nil
}

func mint(t *testing.T, addr, uuid string) int {
	t.Helper()
	body, _ := json.Marshal(map[string]string{"UUID": uuid, "Label": "l"})
	req, _ := http.NewRequest(http.MethodPost, "http://"+addr+"/v1/projects", bytes.NewReader(body))
	req.Header.Set("X-Operator-Secret", "smoke-secret")
	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		t.Fatalf("mint: %v", err)
	}
	resp.Body.Close()
	return resp.StatusCode
}

func mintNoAuth(t *testing.T, addr, uuid string) int {
	t.Helper()
	body, _ := json.Marshal(map[string]string{"UUID": uuid, "Label": "l"})
	resp, err := http.Post("http://"+addr+"/v1/projects", "application/json", bytes.NewReader(body))
	if err != nil {
		t.Fatalf("mint-no-auth: %v", err)
	}
	resp.Body.Close()
	return resp.StatusCode
}

func writeFile0600(t *testing.T, path, content string) {
	t.Helper()
	if err := os.WriteFile(path, []byte(content), 0o600); err != nil {
		t.Fatal(err)
	}
}
