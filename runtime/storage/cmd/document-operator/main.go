// document-operator is explicit offline enrollment/indexing, never a crawler.
package main

import (
	"aifactory.local/storage/internal/budget"
	"aifactory.local/storage/internal/budgetenv"
	"aifactory.local/storage/internal/config"
	"aifactory.local/storage/internal/control"
	"aifactory.local/storage/internal/documents"
	"aifactory.local/storage/internal/registry"
	"aifactory.local/storage/internal/retention"
	"aifactory.local/storage/internal/search"
	"context"
	"encoding/json"
	"flag"
	"fmt"
	"io"
	"os"
	"strings"
	"time"
)

func main() {
	if e := run(); e != nil {
		fmt.Fprintln(os.Stderr, "document-operator:", e)
		os.Exit(1)
	}
}
func run() error {
	state := flag.String("state", "", "current offline control directory")
	dsnFile := flag.String("dsn-file", "", "private PostgreSQL DSN file (index only)")
	exclusive := flag.Bool("exclusive-window", false, "confirm external source/ledger writers are frozen")
	flag.Parse()
	if *state == "" || !*exclusive {
		return fmt.Errorf("state and exclusive source window required")
	}
	var request struct{ Operation, Project, Root, Ledger, ID, Path, ExpectedRevision string }
	dec := json.NewDecoder(io.LimitReader(os.Stdin, 32769))
	dec.DisallowUnknownFields()
	if e := dec.Decode(&request); e != nil {
		return e
	}
	var extra any
	if e := dec.Decode(&extra); e != io.EOF {
		return fmt.Errorf("one bounded request required")
	}
	if request.Project == "" {
		return fmt.Errorf("project required")
	}
	d, e := control.Open(*state)
	if e != nil {
		return e
	}
	defer d.Close()
	cfg := config.Default()
	if request.Operation == "index" {
		st, e := os.Lstat(*dsnFile)
		if e != nil {
			return e
		}
		if !st.Mode().IsRegular() || st.Mode().Perm()&0077 != 0 || st.Size() > 8192 {
			return fmt.Errorf("private bounded DSN file required")
		}
		raw, e := os.ReadFile(*dsnFile)
		if e != nil {
			return e
		}
		cfg.PostgresEnabled = true
		cfg.PostgresDSN = strings.TrimSpace(string(raw))
	}
	env, e := budgetenv.OpenOffline(*state, &cfg)
	if e != nil {
		return e
	}
	defer env.Close()
	if e = d.AttachBudget(env.DetachLedger()); e != nil {
		return e
	}
	op := registry.Principal{ID: "local-document-operator", Kind: registry.Operator}
	return d.WithStableAuthority(op, func(reg *registry.Registry) error {
		if _, _, ok := reg.WorkflowAuthority(request.Project); !ok {
			return registry.ErrUnknownProj
		}
		for _, b := range d.Retention().Barriers() {
			if b.Project == request.Project && b.Scope == retention.ScopeProject {
				return fmt.Errorf("project deletion barrier forbids document enrollment/indexing")
			}
		}
		switch request.Operation {
		case "upsert", "delete":
			target, e := documents.LedgerPath(request.Root, request.Ledger)
			if e != nil {
				return e
			}
			if e = budget.RegisterPath(*state, target, ".document-ledger-", d.Budget()); e != nil {
				return e
			}
			revision, e := documents.UpdateBudgeted(request.Root, request.Ledger, request.ID, request.Path, request.ExpectedRevision, request.Operation == "delete", d.ReserveExternalBytes)
			if e != nil {
				return e
			}
			if e = d.FinishExternal(); e != nil {
				return e
			}
			return json.NewEncoder(os.Stdout).Encode(map[string]any{"status": "updated", "revision": revision})
		case "index":
			st, e := os.Lstat(*dsnFile)
			if e != nil {
				return e
			}
			if !st.Mode().IsRegular() || st.Mode().Perm()&0077 != 0 || st.Size() > 8192 {
				return fmt.Errorf("private bounded DSN file required")
			}
			raw, e := os.ReadFile(*dsnFile)
			if e != nil {
				return e
			}
			ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
			defer cancel()
			store, e := search.Open(ctx, strings.TrimSpace(string(raw)))
			if e != nil {
				return fmt.Errorf("document index unavailable")
			}
			defer store.Close()
			if e = search.MarkRequiredBudgeted(*state, d.ReserveExternalBytes); e != nil {
				return e
			}
			if e = d.FinishExternal(); e != nil {
				return e
			}
			if e = store.ReplaceDocumentsBudgeted(request.Project, request.Root, request.Ledger, request.ExpectedRevision, d.ReserveExternalBytes); e != nil {
				return e
			}
			if e = d.FinishExternal(); e != nil {
				return e
			}
			return json.NewEncoder(os.Stdout).Encode(map[string]any{"status": "indexed", "revision": request.ExpectedRevision})
		default:
			return fmt.Errorf("operation must be upsert, delete or index")
		}
	})
}
