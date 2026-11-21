// workflow-operator performs explicit offline cutover while owning the same control
// lock as the server. Credentials are read only from an operator-owned file.
package main

import (
	"aifactory.local/storage/internal/budget"
	"aifactory.local/storage/internal/budgetenv"
	"aifactory.local/storage/internal/config"
	"aifactory.local/storage/internal/control"
	"aifactory.local/storage/internal/registry"
	"aifactory.local/storage/internal/workflow"
	"context"
	"encoding/json"
	"flag"
	"fmt"
	"os"
	"strings"
	"syscall"
	"time"
)

func run() error {
	state := flag.String("state", "", "existing control state")
	doc := flag.String("document", "", "absolute dedicated generated Markdown file")
	revision := flag.String("revision", "", "SHA-256 of the complete source document")
	direction := flag.String("to", "", "markdown, postgres, or index (no authority transfer)")
	dsnFile := flag.String("dsn-file", "", "0600 PostgreSQL DSN file")
	frozen := flag.Bool("edits-frozen", false, "operator confirms external edits are frozen until completion")
	flag.Parse()
	if !*frozen || *state == "" || *dsnFile == "" {
		return fmt.Errorf("state, DSN file and explicit edit freeze required")
	}
	if *direction != "markdown" && *direction != "postgres" && *direction != "index" {
		return fmt.Errorf("invalid destination")
	}
	f, e := os.OpenFile(*dsnFile, os.O_RDONLY|syscall.O_NOFOLLOW, 0)
	if e != nil {
		return e
	}
	defer f.Close()
	st, e := f.Stat()
	if e != nil {
		return e
	}
	if !st.Mode().IsRegular() || st.Mode().Perm()&0077 != 0 || st.Size() > 16384 {
		return fmt.Errorf("DSN file must be bounded, regular and owner-only")
	}
	b := make([]byte, st.Size())
	if _, e = f.ReadAt(b, 0); e != nil {
		return e
	}
	d, e := control.Open(*state)
	if e != nil {
		return e
	}
	defer d.Close()
	if blocked, _ := d.Blocked(); blocked {
		return control.ErrBlocked
	}
	cfg := config.Default()
	cfg.PostgresEnabled = true
	cfg.PostgresDSN = strings.TrimSpace(string(b))
	env, e := budgetenv.OpenOffline(*state, &cfg)
	if e != nil {
		return e
	}
	defer env.Close()
	if e = d.AttachBudget(env.DetachLedger()); e != nil {
		return e
	}
	if *direction == "markdown" {
		if e = budget.RegisterPath(*state, *doc, ".workflow-cutover-", d.Budget()); e != nil {
			return e
		}
	}
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	s, e := workflow.OpenPostgres(ctx, strings.TrimSpace(string(b)))
	if e != nil {
		return fmt.Errorf("PostgreSQL unavailable or schema incompatible")
	}
	defer s.Close()
	project := flag.Arg(0)
	if project == "" {
		return fmt.Errorf("project UUID required")
	}
	if *direction == "index" {
		if e = workflow.IndexMarkdown(d, s, registry.Principal{ID: "local-operator", Kind: registry.Operator}, project, *doc, *revision); e != nil {
			return e
		}
		return json.NewEncoder(os.Stdout).Encode(map[string]any{"status": "indexed", "project": project, "source_revision": *revision, "authority": "markdown"})
	}
	r, e := workflow.Cutover(d, s, registry.Principal{ID: "local-operator", Kind: registry.Operator}, project, *doc, *revision, registry.WorkflowOwner(*direction))
	if e != nil {
		return e
	}
	return json.NewEncoder(os.Stdout).Encode(r)
}
func main() {
	if e := run(); e != nil {
		fmt.Fprintln(os.Stderr, e)
		os.Exit(1)
	}
}
