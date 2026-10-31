package main

import (
	"aifactory.local/storage/internal/authz"
	"aifactory.local/storage/internal/control"
	"aifactory.local/storage/internal/registry"
	"bytes"
	"strings"
	"testing"
)

func TestOfflineHelperUsesServerAuthority(t *testing.T) {
	d := t.TempDir()
	call := func(init bool, body string) {
		t.Helper()
		args := []string{"-state", d}
		if init {
			args = append(args, "-init")
		}
		var out bytes.Buffer
		if e := run(args, strings.NewReader(body), &out); e != nil {
			t.Fatal(e)
		}
		if strings.Contains(out.String(), "test-secret") {
			t.Fatal("token exposed")
		}
	}
	call(true, `{"Operation":"project","Project":"p","Label":"p"}`)
	call(false, `{"Operation":"consent","Project":"p","Provider":"synthetic","Capability":"capture","Enabled":true}`)
	call(false, `{"Operation":"grant","Grant":{"PrincipalID":"a","Kind":"agent","Projects":{"p":true},"Ops":{"archive.query":true},"Secret":"test-secret"}}`)
	ctl, e := control.Open(d)
	if e != nil {
		t.Fatal(e)
	}
	g, _ := ctl.Registry().Lookup("a")
	tok := authz.Token{PrincipalID: "a", Kind: registry.Agent, Epoch: g.Epoch, Secret: "test-secret"}
	if e = authz.Authorize(ctl.Registry(), tok, "p", registry.OpArchiveQuery); e != nil {
		t.Fatal(e)
	}
	var out bytes.Buffer
	if e = run([]string{"-state", d}, strings.NewReader(`{"Operation":"status"}`), &out); e == nil {
		t.Fatal("helper bypassed active server lock")
	}
	ctl.Close()
	call(false, `{"Operation":"revoke","PrincipalID":"a"}`)
	ctl, e = control.Open(d)
	if e != nil {
		t.Fatal(e)
	}
	defer ctl.Close()
	if e = authz.Authorize(ctl.Registry(), tok, "p", registry.OpArchiveQuery); e == nil {
		t.Fatal("revocation did not survive helper/server handoff")
	}
}
