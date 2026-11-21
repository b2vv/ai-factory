// migration-operator is explicit offline schema maintenance, never startup logic.
package main

import (
	"aifactory.local/storage/internal/backup"
	"aifactory.local/storage/internal/control"
	"aifactory.local/storage/internal/maintenance"
	"aifactory.local/storage/internal/registry"
	"aifactory.local/storage/internal/workflow"
	"context"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"io"
	"os"
	"strings"
	"syscall"
	"time"
)

const backupDependentMigrationsEnabled = false

var errBackupDeferred = errors.New("migration-operator: deferred by release scope; backup-dependent operations are disabled")

func privateFile(path string, max int64) (*os.File, error) {
	fd, e := syscall.Open(path, syscall.O_RDONLY|syscall.O_NOFOLLOW, 0)
	if e != nil {
		return nil, fmt.Errorf("operator input unavailable")
	}
	f := os.NewFile(uintptr(fd), path)
	st, e := f.Stat()
	if e != nil || !st.Mode().IsRegular() || st.Mode().Perm()&0077 != 0 || st.Size() > max {
		f.Close()
		return nil, fmt.Errorf("bounded private input required")
	}
	return f, nil
}
func run(args []string, out io.Writer) error {
	fs := flag.NewFlagSet("migration-operator", flag.ContinueOnError)
	fs.SetOutput(io.Discard)
	state := fs.String("state", "", "current control directory")
	dsnPath := fs.String("pg-dsn-file", "", "private DSN file")
	backupPath := fs.String("backup-file", "", "verified post-cutover snapshot")
	sourcePath := fs.String("sources-file", "", "project to dedicated source path/revision JSON")
	to := fs.Int("to", -1, "target schema, only 0 supported")
	ack := fs.Bool("ack-derived-data-removal", false, "acknowledge verified derived table removal")
	archiveMode := fs.Bool("archive-metadata-v2", false, "explicit archive metadata upgrade")
	apply := fs.Bool("apply", false, "apply archive metadata upgrade")
	project := fs.String("project", "", "archive project")
	configPath := fs.String("config", "", "private explicit backend configuration")
	exclusive := fs.Bool("exclusive-window", false, "external DB and source edits frozen")
	if e := fs.Parse(args); e != nil {
		return e
	}
	if *archiveMode {
		if fs.NArg() != 0 || !*apply || !*exclusive || *state == "" || *project == "" || *configPath == "" || *to != -1 || *ack {
			return fmt.Errorf("archive upgrade requires explicit apply, exclusive window, state, project and private config")
		}
		return runArchiveMigration(*state, *project, *configPath, out)
	}
	if !backupDependentMigrationsEnabled {
		return errBackupDeferred
	}
	if fs.NArg() != 0 || *to != 0 || !*ack || !*exclusive || *state == "" {
		return fmt.Errorf("explicit schema 0, removal acknowledgement and exclusive window required")
	}
	d, e := control.Open(*state)
	if e != nil {
		return e
	}
	defer d.Close()
	if blocked, _ := d.Blocked(); blocked {
		return control.ErrBlocked
	}
	f, e := privateFile(*dsnPath, 16384)
	if e != nil {
		return e
	}
	raw, e := io.ReadAll(f)
	f.Close()
	if e != nil {
		return e
	}
	f, e = privateFile(*sourcePath, 1<<20)
	if e != nil {
		return e
	}
	var sources map[string]maintenance.Source
	dec := json.NewDecoder(f)
	dec.DisallowUnknownFields()
	e = dec.Decode(&sources)
	f.Close()
	if e != nil {
		return e
	}
	inputBackup, e := privateFile(*backupPath, backup.MaxStreamBytes)
	if e != nil {
		return e
	}
	defer inputBackup.Close()
	ctx, cancel := context.WithTimeout(context.Background(), 15*time.Second)
	defer cancel()
	p, e := workflow.OpenPostgresForMaintenance(ctx, strings.TrimSpace(string(raw)))
	if e != nil {
		return fmt.Errorf("database unavailable or schema incompatible")
	}
	defer p.Close()
	if e = maintenance.RollbackWorkflowV1(ctx, d, p, registry.Principal{ID: "local-operator", Kind: registry.Operator}, inputBackup, sources, *ack); e != nil {
		return e
	}
	return json.NewEncoder(out).Encode(map[string]any{"status": "rolled_back", "from": "verified_workflow_and_optional_derived_index", "to": 0, "migration": "0001_workflow.sql"})
}
func main() {
	if e := run(os.Args[1:], os.Stdout); e != nil {
		fmt.Fprintln(os.Stderr, e)
		if errors.Is(e, errBackupDeferred) {
			os.Exit(2)
		}
		os.Exit(1)
	}
}
