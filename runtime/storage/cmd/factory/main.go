// Command factory is a TEST-HARNESS entry point for the Factory control API (PLAN v4
// section 5). It is NOT a supported standalone host distribution: the supported delivery is the
// digest-pinned OCI image plus the operator-only Docker-free helper (owner decision D1).
// It binds loopback only (local-only default; localhost is not authorization), loads the
// durable control registry, and serves the control API. Databases are disabled by
// default; file-based task continuation is independent of this process.
package main

import (
	"context"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"net"
	"net/http"
	"os"
	"os/signal"
	"strings"
	"syscall"
	"time"

	"aifactory.local/storage/internal/api"
	"aifactory.local/storage/internal/config"
	"aifactory.local/storage/internal/control"
)

type operatorToken struct {
	ID     string `json:"id"`
	Secret string `json:"secret"`
}

func main() {
	if err := run(); err != nil {
		fmt.Fprintln(os.Stderr, "factory:", err)
		os.Exit(1)
	}
}

func run() error {
	state := flag.String("state", "", "operator-owned durable state directory (required)")
	listen := flag.String("listen", "127.0.0.1:0", "loopback listen address (host must be loopback)")
	cfgPath := flag.String("config", "", "optional JSON config file (overlays D4 defaults)")
	tokenPath := flag.String("operator-token", "", "path to the 0600 operator token file {id,secret} (required)")
	doInit := flag.Bool("init", false, "explicit first-time operator initialization of -state, then exit (refuses to reset existing/partial/corrupt state)")
	devAllowNonLoopback := flag.Bool("dev-allow-nonloopback", false, "DEV/TEST ONLY: permit a non-loopback -listen bind (e.g. 0.0.0.0 inside a container whose port is published ONLY to the host's 127.0.0.1). Normal startup stays loopback-only by default; this must be set EXPLICITLY. It changes nothing about authentication/authorization - operator and agent credentials are still required and checked.")
	flag.Parse()

	if *state == "" {
		return errors.New("-state is required")
	}

	// A: initialization is an explicit, separate operator gesture. Normal startup never
	// creates authority; `-init` creates a brand-new registry and exits. It refuses to run
	// against any non-pristine state (existing marker, surviving records, or a
	// corrupt/ambiguous log), so it can never become a recovery bypass.
	if *doInit {
		ctl, err := control.Initialize(*state)
		if err != nil {
			return err
		}
		defer ctl.Close()
		fmt.Printf("INITIALIZED %s\n", *state)
		return nil
	}

	if *tokenPath == "" {
		return errors.New("-operator-token is required")
	}
	// Default contract: loopback-only bind. A non-loopback bind is allowed ONLY when the
	// operator explicitly opts in (dev/test container mode), and even then the intended
	// deployment publishes the container port to the host's 127.0.0.1 only. This gate does
	// not relax authentication; it only lets the process bind a container-internal 0.0.0.0.
	if *devAllowNonLoopback {
		fmt.Fprintf(os.Stderr, "factory: WARNING: -dev-allow-nonloopback is set; binding %q WITHOUT the loopback-only guard (dev/test container mode). Publish the port to host 127.0.0.1 only; never expose to LAN/internet.\n", *listen)
	} else if err := requireLoopback(*listen); err != nil {
		return err
	}

	tok, err := readOperatorToken(*tokenPath)
	if err != nil {
		return err
	}

	cfg, err := config.Load(*cfgPath, os.Getenv)
	if err != nil {
		return err
	}

	// Normal startup opens EXISTING state. An uninitialized or mistyped -state path does not
	// silently initialize: control.Open returns a BLOCKED registry, surfaced on /health and
	// denying all authority, until an operator runs `-init` (for a genuinely new dir) or
	// recovers a damaged one.
	ctl, err := control.Open(*state)
	if err != nil {
		return err
	}
	defer ctl.Close()
	if blocked, reason := ctl.Blocked(); blocked {
		// Start anyway so /health is observable, but make the fail-closed state loud.
		fmt.Fprintln(os.Stderr, "factory: control registry BLOCKED:", reason)
	}

	srv := api.New(ctl, cfg, tok.ID, tok.Secret)
	ln, err := net.Listen("tcp", *listen)
	if err != nil {
		return err
	}
	// Announce the bound address (never the secret) so a supervisor/test can reach it.
	fmt.Printf("LISTEN %s\n", ln.Addr().String())

	httpSrv := &http.Server{Handler: srv.Handler(), ReadHeaderTimeout: 5 * time.Second}

	ctx, stop := signal.NotifyContext(context.Background(), syscall.SIGINT, syscall.SIGTERM)
	defer stop()
	errCh := make(chan error, 1)
	go func() { errCh <- httpSrv.Serve(ln) }()

	select {
	case <-ctx.Done():
		shutCtx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
		defer cancel()
		return httpSrv.Shutdown(shutCtx)
	case err := <-errCh:
		if errors.Is(err, http.ErrServerClosed) {
			return nil
		}
		return err
	}
}

// requireLoopback rejects a non-loopback bind so the default deployment is local-only.
func requireLoopback(addr string) error {
	host, _, err := net.SplitHostPort(addr)
	if err != nil {
		return fmt.Errorf("invalid -listen %q: %w", addr, err)
	}
	if host == "localhost" {
		return nil
	}
	ip := net.ParseIP(host)
	if ip == nil || !ip.IsLoopback() {
		return fmt.Errorf("-listen host %q is not loopback (local-only default)", host)
	}
	return nil
}

// readOperatorToken loads the bootstrap operator credential. The secret is read from a
// 0600 file and never printed; a too-permissive mode is reported honestly (the same-user
// trust limit still applies: 0600 guards other users, not another process of this user).
func readOperatorToken(path string) (operatorToken, error) {
	info, err := os.Stat(path)
	if err != nil {
		return operatorToken{}, err
	}
	if mode := info.Mode().Perm(); mode&0o077 != 0 {
		fmt.Fprintf(os.Stderr, "factory: warning: operator token %s has mode %o; expected 0600\n", path, mode)
	}
	b, err := os.ReadFile(path)
	if err != nil {
		return operatorToken{}, err
	}
	var tok operatorToken
	if err := json.Unmarshal(b, &tok); err != nil {
		return operatorToken{}, fmt.Errorf("operator token: malformed JSON: %w", err)
	}
	if strings.TrimSpace(tok.ID) == "" || strings.TrimSpace(tok.Secret) == "" {
		return operatorToken{}, errors.New("operator token: id and secret are required")
	}
	return tok, nil
}
