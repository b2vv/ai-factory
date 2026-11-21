// identity-operator is the Docker-free operator helper. It opens the SAME durable
// registry as the server under its exclusive lock; no second authority or HTTP API.
// The state-directory OS owner is the trust boundary. Input may contain secrets;
// output never echoes grant tokens. Do not invoke this from untrusted agent hooks.
package main

import (
	"aifactory.local/storage/internal/budgetenv"
	"aifactory.local/storage/internal/config"
	"aifactory.local/storage/internal/control"
	"aifactory.local/storage/internal/registry"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"io"
	"os"
)

type request struct {
	Operation   string
	Project     string
	Label       string
	Provider    string
	Capability  string
	Enabled     bool
	Location    registry.Location
	Confirm     bool
	Grant       registry.Grant
	PrincipalID string
}

func run(args []string, input io.Reader, out io.Writer) error {
	fs := flag.NewFlagSet("identity-operator", flag.ContinueOnError)
	fs.SetOutput(io.Discard)
	state := fs.String("state", "", "existing control state directory")
	init := fs.Bool("init", false, "explicitly initialize an empty registry")
	if e := fs.Parse(args); e != nil {
		return e
	}
	if *state == "" {
		return errors.New("-state is required")
	}
	if fs.NArg() != 0 {
		return errors.New("unexpected arguments")
	}
	var d *control.Durable
	var e error
	if *init {
		d, e = control.InitializeBudgeted(*state, config.Default())
	} else {
		d, e = control.Open(*state)
	}
	if e != nil {
		return e
	}
	defer d.Close()
	env, e := budgetenv.Open(*state, nil)
	if e != nil {
		return e
	}
	defer env.Close()
	if e = d.AttachBudget(env.DetachLedger()); e != nil {
		return e
	}
	if b, _ := d.Blocked(); b {
		return control.ErrBlocked
	}
	var r request
	dec := json.NewDecoder(io.LimitReader(input, 1<<20))
	dec.DisallowUnknownFields()
	if e = dec.Decode(&r); e != nil {
		return fmt.Errorf("invalid operator request: %w", e)
	}
	var extra any
	if e = dec.Decode(&extra); e != io.EOF {
		return errors.New("one JSON request required")
	}
	op := registry.Principal{ID: "local-operator", Kind: registry.Operator}
	result := map[string]any{"operation": r.Operation, "api_available": false}
	switch r.Operation {
	case "status":
		result["projects"] = d.Registry().Projects()
	case "project":
		e = d.MintProject(op, r.Project, r.Label)
	case "enroll":
		result["status"], e = d.EnrollLocation(op, r.Project, r.Location, r.Confirm)
	case "consent":
		result["epoch"], e = d.SetConsent(op, r.Project, r.Provider, r.Capability, r.Enabled)
	case "grant":
		e = d.IssueGrant(op, r.Grant)
		if e == nil {
			g, _ := d.Registry().Lookup(r.Grant.PrincipalID)
			result["epoch"] = g.Epoch
		}
	case "revoke":
		e = d.RevokeGrant(op, r.PrincipalID)
	default:
		return errors.New("unknown operation")
	}
	if e != nil {
		return e
	}
	result["status"] = "applied"
	return json.NewEncoder(out).Encode(result)
}
func main() {
	if e := run(os.Args[1:], os.Stdin, os.Stdout); e != nil {
		fmt.Fprintln(os.Stderr, e)
		os.Exit(1)
	}
}
