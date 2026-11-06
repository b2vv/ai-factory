package main

import (
	"go/ast"
	"go/parser"
	"go/token"
	"testing"
)

// This is a structural ordering contract, complementary to real process recovery
// and fail-closed tests; it does not claim a general control-flow proof.
func TestStartupRecoveryOrderingContract(t *testing.T) {
	f, err := parser.ParseFile(token.NewFileSet(), "main.go", nil, 0)
	if err != nil {
		t.Fatal(err)
	}
	var run *ast.FuncDecl
	for _, d := range f.Decls {
		if fn, ok := d.(*ast.FuncDecl); ok && fn.Name.Name == "run" {
			run = fn
		}
	}
	if run == nil {
		t.Fatal("startup function absent")
	}
	var worker, listen token.Pos
	counts := map[string]int{}
	var recovery []token.Pos
	ast.Inspect(run.Body, func(n ast.Node) bool {
		if call, ok := n.(*ast.CallExpr); ok {
			if id, ok := call.Fun.(*ast.Ident); ok && id.Name == "drainWorker" {
				worker = call.Pos()
			}
			if s, ok := call.Fun.(*ast.SelectorExpr); ok && s.Sel.Name == "Listen" {
				if id, ok := s.X.(*ast.Ident); ok && id.Name == "net" {
					listen = call.Pos()
				}
			}
		}
		stmt, ok := n.(*ast.IfStmt)
		if !ok {
			return true
		}
		assign, ok := stmt.Init.(*ast.AssignStmt)
		if !ok || len(assign.Rhs) != 1 {
			return true
		}
		call, ok := assign.Rhs[0].(*ast.CallExpr)
		if !ok {
			return true
		}
		sel, ok := call.Fun.(*ast.SelectorExpr)
		if !ok {
			return true
		}
		name := sel.Sel.Name
		if name != "RecoverArchive" && name != "RecoverIndex" {
			return true
		}
		receiver, ok := sel.X.(*ast.Ident)
		if !ok || receiver.Name != "srv" || len(assign.Lhs) != 1 {
			t.Fatal("unexpected recovery receiver or binding")
		}
		binding, ok := assign.Lhs[0].(*ast.Ident)
		if !ok || binding.Name != "err" || assign.Tok != token.DEFINE {
			t.Fatal("recovery error binding changed")
		}
		// No deferred function or goroutine may contain the recovery call.
		ast.Inspect(run.Body, func(parent ast.Node) bool {
			switch x := parent.(type) {
			case *ast.GoStmt:
				if x.Pos() <= call.Pos() && call.End() <= x.End() {
					t.Error("asynchronous startup recovery")
				}
			case *ast.FuncLit:
				if x.Pos() <= call.Pos() && call.End() <= x.End() {
					t.Error("recovery inside deferred function")
				}
			}
			return true
		})
		cond, ok := stmt.Cond.(*ast.BinaryExpr)
		if !ok || cond.Op != token.NEQ {
			t.Fatal("recovery error not checked")
		}
		lhs, lok := cond.X.(*ast.Ident)
		rhs, rok := cond.Y.(*ast.Ident)
		if !lok || !rok || lhs.Name != "err" || rhs.Name != "nil" {
			t.Fatal("unexpected error condition")
		}
		if len(stmt.Body.List) != 1 {
			t.Fatal("recovery error must return immediately")
		}
		ret, ok := stmt.Body.List[0].(*ast.ReturnStmt)
		if !ok || len(ret.Results) != 1 {
			t.Fatal("recovery error not returned")
		}
		id, ok := ret.Results[0].(*ast.Ident)
		if !ok || id.Name != "err" {
			t.Fatal("recovery error discarded")
		}
		counts[name]++
		recovery = append(recovery, call.Pos())
		return true
	})
	if counts["RecoverArchive"] != 1 || counts["RecoverIndex"] != 2 {
		t.Fatal("missing synchronous recovery branches", counts)
	}
	if worker == 0 || listen == 0 || worker >= listen {
		t.Fatal("worker/readiness order changed")
	}
	for _, p := range recovery {
		if p >= worker || p >= listen {
			t.Fatal("recovery follows background worker or readiness")
		}
	}
}
