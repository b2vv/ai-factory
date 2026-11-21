// backup-operator is an explicit offline operator command, not an agent hook.
package main

import (
	"aifactory.local/storage/internal/archive"
	"aifactory.local/storage/internal/backup"
	"aifactory.local/storage/internal/config"
	"aifactory.local/storage/internal/control"
	"aifactory.local/storage/internal/registry"
	"aifactory.local/storage/internal/workflow"
	"context"
	"encoding/json"
	"flag"
	"fmt"
	"io"
	"os"
	"strings"
	"syscall"
	"time"
)

func secret(path string) (string, error) {
	fd, e := syscall.Open(path, syscall.O_RDONLY|syscall.O_NOFOLLOW, 0)
	if e != nil {
		return "", fmt.Errorf("credential file unavailable")
	}
	f := os.NewFile(uintptr(fd), path)
	defer f.Close()
	st, e := f.Stat()
	if e != nil || !st.Mode().IsRegular() || st.Mode().Perm()&0077 != 0 || st.Size() > 16384 {
		return "", fmt.Errorf("private bounded credential file required")
	}
	b, e := io.ReadAll(io.LimitReader(f, 16385))
	if e != nil {
		return "", fmt.Errorf("credential read failed")
	}
	return strings.TrimSpace(string(b)), nil
}
func run(args []string, out io.Writer) error {
	fs := flag.NewFlagSet("backup-operator", flag.ContinueOnError)
	fs.SetOutput(io.Discard)
	mode := fs.String("mode", "", "create, restore or expire")
	state := fs.String("state", "", "current control directory")
	directory := fs.String("directory", "", "existing private backup directory")
	name := fs.String("name", "", "snapshot.backup")
	mongoFile := fs.String("mongo-uri-file", "", "private Mongo URI file")
	pgFile := fs.String("pg-dsn-file", "", "private PG DSN file")
	db := fs.String("mongo-db", "", "explicit archive database")
	collection := fs.String("mongo-collection", "", "explicit archive collection")
	projects := fs.String("projects", "", "comma-separated project UUIDs for create")
	exclusive := fs.Bool("exclusive-window", false, "operator confirms no other writers to either database")
	budget := fs.Int64("budget-bytes", config.DefaultBackupBudget, "aggregate backup budget")
	headroom := fs.Int64("free-headroom", config.DefaultFreeHeadroom, "free-space floor")
	if e := fs.Parse(args); e != nil {
		return e
	}
	if fs.NArg() != 0 || !*exclusive || *state == "" || (*mode != "expire" && (*db == "" || *collection == "")) || (*mode != "create" && *mode != "restore" && *mode != "expire") {
		return fmt.Errorf("explicit mode, state, database, collection and exclusive window required")
	}
	d, e := control.Open(*state)
	if e != nil {
		return e
	}
	defer d.Close()
	if blocked, _ := d.Blocked(); blocked {
		return control.ErrBlocked
	}
	repo, e := backup.OpenRepository(*directory, *budget, *headroom)
	if e != nil {
		return e
	}
	defer repo.Close()
	if *mode == "expire" {
		result, err := repo.Expire(time.Now())
		status := "expired"
		if err != nil {
			status = "incomplete"
		}
		if e := json.NewEncoder(out).Encode(map[string]any{"status": status, "result": result}); e != nil {
			return e
		}
		return err
	}

	uri, e := secret(*mongoFile)
	if e != nil {
		return e
	}
	dsn, e := secret(*pgFile)
	if e != nil {
		return e
	}
	ctx, cancel := context.WithTimeout(context.Background(), 15*time.Second)
	defer cancel()
	a, e := archive.OpenMongo(ctx, uri, *db, *collection)
	if e != nil {
		return fmt.Errorf("archive unavailable")
	}
	defer a.Close()
	p, e := workflow.OpenPostgres(ctx, dsn)
	if e != nil {
		return fmt.Errorf("workflow unavailable or schema incompatible")
	}
	defer p.Close()
	op := registry.Principal{ID: "local-operator", Kind: registry.Operator}
	if *mode == "create" {
		if *projects == "" {
			return fmt.Errorf("explicit project list required")
		}
		if e = repo.Save(*name, func(w io.Writer) error { return backup.CreateStream(d, op, a, p, strings.Split(*projects, ","), w) }); e != nil {
			return e
		}
		return json.NewEncoder(out).Encode(map[string]string{"status": "published", "name": *name})
	}
	input, e := repo.Open(*name)
	if e != nil {
		return e
	}
	defer input.Close()
	result, e := backup.RestoreFile(d, op, a, p, input, time.Now())
	if e != nil {
		json.NewEncoder(out).Encode(map[string]any{"status": "incomplete_keep_offline", "result": result})
		return fmt.Errorf("restore incomplete; keep target offline: %w", e)
	}
	return json.NewEncoder(out).Encode(map[string]any{"status": "restored", "result": result})
}
func main() {
	fmt.Fprintln(os.Stderr, "backup-operator: deferred by release scope; backup-dependent operations are disabled")
	os.Exit(2)

	if e := run(os.Args[1:], os.Stdout); e != nil {
		fmt.Fprintln(os.Stderr, e)
		os.Exit(1)
	}
}
