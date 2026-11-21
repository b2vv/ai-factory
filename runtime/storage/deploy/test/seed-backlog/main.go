// Synthetic process-harness fixture, not a capture entrypoint. The server must be
// stopped; its exclusive control lock prevents accidental concurrent mutation.
package main

import (
	"aifactory.local/storage/internal/archive"
	"aifactory.local/storage/internal/config"
	"aifactory.local/storage/internal/control"
	"aifactory.local/storage/internal/ingest"
	"fmt"
	"os"
	"path/filepath"
)

func run() error {
	if os.Getenv("FACTORY_SYNTHETIC_FIXTURE") != "1" || len(os.Args) != 2 {
		return fmt.Errorf("synthetic fixture opt-in and state path required")
	}
	d, e := control.Open(os.Args[1])
	if e != nil {
		return e
	}
	defer d.Close()
	if b, _ := d.Blocked(); b {
		return control.ErrBlocked
	}
	c := d.Registry().ConsentEpoch("offline-project", "synthetic", "capture")
	if !c.Enabled {
		return fmt.Errorf("synthetic project consent required")
	}
	i, e := ingest.Open(filepath.Join(os.Args[1], "ingest", "wal"), config.NewAccountant(config.Default()), archive.NewMemStore())
	if e != nil {
		return e
	}
	defer i.Close()
	r := archive.Record{Project: "offline-project", Provider: "synthetic", SourceInstance: "fixture", SessionID: "startup", MessageID: "pending", Type: archive.TypeMessage, Role: "user", Text: "synthetic accepted backlog", ConsentEpoch: c.Epoch}
	_, e = i.Accept(archive.IdentityKey(r), r, config.Usage{FreeBytes: 1 << 40})
	return e
}
func main() {
	if e := run(); e != nil {
		fmt.Fprintln(os.Stderr, e)
		os.Exit(1)
	}
}
