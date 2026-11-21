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
	"path/filepath"
	"strings"
	"syscall"
	"time"

	"aifactory.local/storage/internal/api"
	"aifactory.local/storage/internal/archive"
	"aifactory.local/storage/internal/budgetenv"
	"aifactory.local/storage/internal/config"
	"aifactory.local/storage/internal/control"
	"aifactory.local/storage/internal/ingest"
	"aifactory.local/storage/internal/meter"
	"aifactory.local/storage/internal/registry"
	"aifactory.local/storage/internal/search"
	"aifactory.local/storage/internal/summary"
	"aifactory.local/storage/internal/workflow"
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
	extracts := flag.Bool("session-extracts", false, "opt in to asynchronous local prefix extracts; existing summary consent and metadata schema required")
	extractPlan := summary.DefaultConfig()
	extractOptions := summary.DefaultExtractOptions()
	flag.DurationVar(&extractPlan.ActiveAfter, "extract-active-after", extractPlan.ActiveAfter, "active-session eligibility deadline from first uncovered capture")
	flag.DurationVar(&extractPlan.IdleAfter, "extract-idle-after", extractPlan.IdleAfter, "idle-session eligibility deadline from last uncovered capture")
	extractPoll := flag.Duration("extract-poll", 5*time.Second, "bounded session discovery interval; backlog adds latency")
	flag.IntVar(&extractPlan.MaxInputBytes, "extract-max-input", extractPlan.MaxInputBytes, "whole-record input byte safeguard")
	flag.IntVar(&extractPlan.MaxReferenceBytes, "extract-max-references", extractPlan.MaxReferenceBytes, "coverage reference byte cap")
	flag.IntVar(&extractOptions.MaxExcerptBytes, "extract-max-excerpt", extractOptions.MaxExcerptBytes, "literal UTF-8 prefix bytes per source")
	flag.IntVar(&extractOptions.MaxDocumentBytes, "extract-max-document", extractOptions.MaxDocumentBytes, "complete extract document byte admission cap")
	flag.Parse()

	if *state == "" {
		return errors.New("-state is required")
	}

	cfg, err := config.Load(*cfgPath, os.Getenv)
	if err != nil {
		return err
	}

	if err := extractPlan.Validate(); err != nil {
		return err
	}
	if _, err := summary.ExtractiveVersion(extractOptions); err != nil {
		return err
	}
	if *extractPoll <= 0 {
		return errors.New("extract-poll must be positive")
	}
	if *extracts && !cfg.MongoEnabled {
		return errors.New("session-extracts requires the enabled Mongo archive")
	}

	// A: initialization is an explicit, separate operator gesture. Normal startup never
	// creates authority; `-init` creates a brand-new registry and exits. It refuses to run
	// against any non-pristine state (existing marker, surviving records, or a
	// corrupt/ambiguous log), so it can never become a recovery bypass.
	if *doInit {
		ctl, err := control.InitializeBudgeted(*state, cfg)
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
		if cfg.MongoEnabled {
			return errors.New("archive startup refused while control authority is blocked")
		}
	}

	metadataActive := false
	if blocked, _ := ctl.Blocked(); !blocked {
		for _, project := range ctl.Registry().Projects() {
			state, active, err := ctl.ArchiveState(project)
			if err != nil {
				return err
			}
			if !active {
				continue
			}
			metadataActive = true
			if !state.MigrationComplete {
				return errors.New("archive metadata migration incomplete; resume offline migration")
			}
		}
		if metadataActive && !cfg.MongoEnabled {
			return errors.New("archive metadata requires enabled authoritative source")
		}
	}

	var budgetEnv *budgetenv.Environment
	if blocked, _ := ctl.Blocked(); !blocked {
		budgetEnv, err = budgetenv.Open(*state, &cfg)
		if err != nil {
			return err
		}
		defer budgetEnv.Close()
		if err = ctl.AttachBudget(budgetEnv.DetachLedger()); err != nil {
			return err
		}
	}
	srv := api.New(ctl, cfg, tok.ID, tok.Secret)

	// Composition root: open the REAL backends when enabled. An enabled-but-unreachable
	// backend is a hard startup error (fail-closed) - never a fabricated healthy and never
	// an in-memory fake substitution in DB mode. A background pinger refreshes availability
	// so /health reflects the live backend state and flips to down on a runtime outage.
	pingCtx, pingStop := context.WithCancel(context.Background())
	defer pingStop()
	var mongoStore *archive.MongoStore
	var pgStore *workflow.PGStore
	if cfg.MongoEnabled {
		openCtx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
		mongoStore, err = archive.OpenMongo(openCtx, cfg.MongoURI, cfg.MongoDB, cfg.MongoCollection)
		cancel()
		if err != nil {
			return fmt.Errorf("archive backend (mongo) enabled but unreachable: %w", err)
		}
		defer mongoStore.Close()
	}
	if cfg.PostgresEnabled {
		openCtx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
		pgStore, err = workflow.OpenPostgres(openCtx, cfg.PostgresDSN)
		cancel()
		if err != nil {
			return fmt.Errorf("workflow backend (postgres) enabled but unreachable: %w", err)
		}
		defer pgStore.Close()
	}
	stateDir := *state
	ingWalDir := filepath.Join(stateDir, "ingest", "wal")
	if budgetEnv != nil {
		srv.SetSharedUsageMeter(budgetEnv.Usage)
	} else {
		srv.SetSharedUsageMeter(func() (config.Usage, error) { return measureUsage(stateDir, ingWalDir, mongoStore, pgStore) })
	}
	var ing *ingest.Ingestor
	if cfg.MongoEnabled {
		openIntake := ingest.Open
		if metadataActive {
			openIntake = ingest.OpenExisting
		}
		ing, err = openIntake(ingWalDir, config.NewAccountant(cfg), mongoStore)
		if err != nil {
			return fmt.Errorf("capture ingestion WAL open failed: %w", err)
		}
		defer ing.Close()
		if ctl.Budget() != nil {
			if err := ing.SetBudget(ctl.Budget()); err != nil {
				return err
			}
		}
		srv.SetIngestor(ing)
	}
	if blocked, _ := ctl.Blocked(); !blocked {
		if err := srv.RecoverArchive(); err != nil {
			return err
		}
	}

	required, indexMarkerErr := search.Required(*state)
	if indexMarkerErr != nil {
		return indexMarkerErr
	}
	srv.SetSearchRequired(required)
	if pgStore != nil {
		indexCtx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
		index, indexErr := search.Open(indexCtx, cfg.PostgresDSN)
		cancel()
		if indexErr != nil {
			return fmt.Errorf("derived search index startup failed: %w", indexErr)
		}
		defer index.Close()
		srv.SetSearchStore(index)
		if blocked, _ := ctl.Blocked(); !blocked {
			if err := srv.RecoverIndex(); err != nil {
				return err
			}
		}
		// A blocked registry still exposes health, but cannot start indexing. Its
		// capability marker is admitted after recovery on the next ordinary startup.
		if blocked, _ := ctl.Blocked(); !blocked {
			if err := ctl.WithStableAuthority(registry.Principal{Kind: registry.Operator}, func(_ *registry.Registry) error {
				if e := search.MarkRequiredBudgeted(*state, ctl.ReserveExternalBytes); e != nil {
					return e
				}
				return ctl.FinishExternal()
			}); err != nil {
				return err
			}
		}
		srv.SetSearchStore(index)
	}
	if pgStore == nil {
		if blocked, _ := ctl.Blocked(); !blocked {
			if err := srv.RecoverIndex(); err != nil {
				return err
			}
		}
	}

	srv.SetAvailability(archiveProbe(mongoStore), pgProbe(pgStore))
	if pgStore != nil {
		srv.SetWorkflowStore(pgStore)
	}
	if mongoStore != nil || pgStore != nil {
		go pingLoop(pingCtx, mongoStore, pgStore)
	}

	if *extracts {
		if err := srv.ConfigureSummaries(extractPlan, extractOptions); err != nil {
			return err
		}
	}

	// Archive access/replay remains available when new capture is disabled. The
	// capture endpoints enforce CaptureEnabled independently; current consent/barriers
	// still govern every replay and read of previously accepted records.
	if ing != nil {
		// R5: background drain/replay worker. It projects WAL records to the archive WITHOUT a
		// new producer request — a startup replay plus a periodic cycle, so records left durable
		// by a crash (accepted but not yet archive-committed) or by a transient Mongo outage are
		// drained on recovery. It shares the server mutation lock (via DrainOnce) so it can never
		// publish while a purge holds it, and it releases the lock during its backoff sleep.
		//
		// Shutdown ordering (V2 P2): the worker is STOPPED and JOINED before the ingestor/WAL is
		// closed, so it can never drain against a closed WAL. The worker's stop+join defer is
		// registered AFTER ing.Close's defer, so (LIFO) it runs FIRST on return.
		workerCtx, workerStop := context.WithCancel(pingCtx)
		workerDone := make(chan struct{})
		go func() {
			defer close(workerDone)
			drainWorkerProjects(workerCtx, srv, func() int { return len(ctl.Registry().Projects()) })
		}()
		defer func() { workerStop(); <-workerDone }()
	}

	if *extracts {
		stopExtracts := startSessionExtractWorker(pingCtx, srv, *extractPoll)
		// LIFO: stop/join generation before drain and before intake/control close.
		defer stopExtracts()
	}

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

// measureUsage computes live D4 capacity usage including BOTH enabled DB backends toward the
// live-data cap: the Mongo archive (storageSize+indexSize) and the PostgreSQL index/working
// copy (pg_database_size). A measurement error (filesystem or either dbStats) is returned so
// admission fails closed (never read as unlimited).
func measureUsage(stateDir, walDir string, store *archive.MongoStore, pg *workflow.PGStore) (config.Usage, error) {
	var extra int64
	if store != nil {
		mctx, cancel := context.WithTimeout(context.Background(), 3*time.Second)
		sz, err := store.StorageBytes(mctx)
		cancel()
		if err != nil {
			return config.Usage{}, fmt.Errorf("archive storage size: %w", err)
		}
		extra += sz
	}
	if pg != nil {
		pctx, cancel := context.WithTimeout(context.Background(), 3*time.Second)
		sz, err := pg.StorageBytes(pctx)
		cancel()
		if err != nil {
			return config.Usage{}, fmt.Errorf("workflow (postgres) storage size: %w", err)
		}
		extra += sz
	}
	return meter.Measure(stateDir, walDir, extra)
}

// archiveProbe/pgProbe expose a store's live availability as a probe func (nil when the
// backend is disabled, which /health reports as down).
func archiveProbe(s *archive.MongoStore) func() bool {
	if s == nil {
		return nil
	}
	return s.Available
}

func pgProbe(s *workflow.PGStore) func() bool {
	if s == nil {
		return nil
	}
	return s.Available
}

// pingLoop periodically refreshes each enabled backend's availability so /health reflects
// the live state (and a runtime outage flips it to down within one interval).
func pingLoop(ctx context.Context, m *archive.MongoStore, p *workflow.PGStore) {
	t := time.NewTicker(2 * time.Second)
	defer t.Stop()
	for {
		select {
		case <-ctx.Done():
			return
		case <-t.C:
			if m != nil {
				pc, cancel := context.WithTimeout(ctx, 3*time.Second)
				_ = m.Ping(pc)
				cancel()
			}
			if p != nil {
				pc, cancel := context.WithTimeout(ctx, 3*time.Second)
				_ = p.Ping(pc)
				cancel()
			}
		}
	}
}

// drainWorker periodically projects durable-accepted WAL records to the archive via the
// server's shared, lock-serialized DrainOnce. On success it uses a short base interval; on an
// error (archive unavailable / BLOCKED journal) it backs off up to a cap. It NEVER holds the
// mutation lock during the backoff sleep (DrainOnce takes and releases it per cycle). The
// serve-gate inside DrainOnce quarantines revoked/barred records, so the worker never
// publishes something a purge/revoke withheld.
func drainWorker(ctx context.Context, srv *api.Server) {
	drainWorkerProjects(ctx, srv, func() int { return 1 })
}

func drainWorkerProjects(ctx context.Context, srv *api.Server, projectCount func() int) {
	const base, max = 2 * time.Second, 30 * time.Second
	backoff := base
	busySweeps := 0
	for {
		_, drainErr := srv.DrainOnce()
		if drainErr != nil {
			if backoff *= 2; backoff > max {
				backoff = max
			}
		} else {
			backoff = base
		}
		// Derived PG failures never undo or hold Mongo archive commitment.
		advanced, indexErr := indexSweep(ctx, projectCount(), srv.IndexOnceProgress)
		delay, nextBusy := nextIndexDelay(backoff, drainErr == nil, indexErr == nil, advanced, busySweeps)
		busySweeps = nextBusy
		select {
		case <-ctx.Done():
			return
		case <-time.After(delay):
		}
	}
}

func nextIndexDelay(backoff time.Duration, drainOK, indexOK, advanced bool, busySweeps int) (time.Duration, int) {
	if drainOK && indexOK && advanced && busySweeps < 8 {
		return 25 * time.Millisecond, busySweeps + 1
	}
	return backoff, 0
}

// Each call releases the server/control locks. Finite sweeps and bursts let
// cancellation, capture and quiet/error backoff run between catch-up steps.
func indexSweep(ctx context.Context, projects int, step func() (int, bool, error)) (bool, error) {
	if projects < 1 {
		projects = 1
	}
	if projects > 64 {
		projects = 64
	}
	advanced := false
	for n := 0; n < projects; n++ {
		if err := ctx.Err(); err != nil {
			return advanced, err
		}
		_, progress, err := step()
		if err != nil {
			return advanced, err
		}
		advanced = advanced || progress
	}
	return advanced, nil
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

// Generation never runs in a capture request. Cancellation is checked between
// bounded reads; legacy backend calls may overrun by their existing timeout.
func sessionExtractWorker(ctx context.Context, srv *api.Server, poll time.Duration) {
	for {
		if ctx.Err() != nil {
			return
		}
		_, _ = srv.SummaryOnce(ctx, time.Now().UTC())
		timer := time.NewTimer(poll)
		select {
		case <-ctx.Done():
			timer.Stop()
			return
		case <-timer.C:
		}
	}
}

// Own the worker lifetime: cancellation stops the next safe boundary, and joining
// preserves resource-close ordering even while a legacy source call finishes.
func startSessionExtractWorker(parent context.Context, srv *api.Server, poll time.Duration) func() {
	ctx, cancel := context.WithCancel(parent)
	done := make(chan struct{})
	go func() { defer close(done); sessionExtractWorker(ctx, srv, poll) }()
	return func() { cancel(); <-done }
}
