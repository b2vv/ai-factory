package budgetenv

import (
	"errors"
	"testing"
	"time"
)

type fakeInv struct{ total int64 }

type passLog struct {
	calls []bool // true = incremental (prev given), false = full
	next  int64
	err   error
}

func (l *passLog) pass(prev *fakeInv) (*fakeInv, error) {
	l.calls = append(l.calls, prev != nil)
	if l.err != nil {
		return nil, l.err
	}
	return &fakeInv{total: l.next}, nil
}

func total(i *fakeInv) int64 { return i.total }

func TestInventoryCacheReusesRefreshesAndRebuilds(t *testing.T) {
	now := time.Unix(1000, 0)
	clock = func() time.Time { return now }
	defer func() { clock = time.Now }()
	var c inventoryCache[fakeInv]
	l := &passLog{next: 10}
	if v, _ := c.get("a", l.pass, total); v != 10 || len(l.calls) != 1 || l.calls[0] {
		t.Fatalf("first read must be full: %d %v", v, l.calls)
	}
	now = now.Add(sampleMaxAge - time.Second)
	if v, _ := c.get("a", l.pass, total); v != 10 || len(l.calls) != 1 {
		t.Fatalf("unchanged fresh token must reuse: %d %v", v, l.calls)
	}
	l.next = 11
	if v, _ := c.get("b", l.pass, total); v != 11 || len(l.calls) != 2 || !l.calls[1] {
		t.Fatalf("changed token must refresh incrementally: %d %v", v, l.calls)
	}
	now = now.Add(sampleMaxAge)
	l.next = 12
	if v, _ := c.get("b", l.pass, total); v != 12 || len(l.calls) != 3 || !l.calls[2] {
		t.Fatalf("old value must refresh incrementally: %d %v", v, l.calls)
	}
	now = now.Add(fullCheckEvery)
	l.next = 13
	if v, _ := c.get("b", l.pass, total); v != 13 || len(l.calls) != 4 || l.calls[3] {
		t.Fatalf("periodic full check must rebuild: %d %v", v, l.calls)
	}
	now = now.Add(-time.Hour)
	l.next = 14
	if v, _ := c.get("b", l.pass, total); v != 14 || len(l.calls) != 5 || l.calls[4] {
		t.Fatalf("clock moving back must rebuild: %d %v", v, l.calls)
	}
}

func TestInventoryCacheDropsEverythingAfterAFailedPass(t *testing.T) {
	now := time.Unix(1000, 0)
	clock = func() time.Time { return now }
	defer func() { clock = time.Now }()
	var c inventoryCache[fakeInv]
	l := &passLog{next: 5}
	if _, err := c.get("a", l.pass, total); err != nil {
		t.Fatal(err)
	}
	boom := errors.New("backend down")
	l.err = boom
	if _, err := c.get("b", l.pass, total); !errors.Is(err, boom) {
		t.Fatalf("error must surface: %v", err)
	}
	if c.inv != nil {
		t.Fatal("a failed pass must leave no inventory")
	}
	l.err, l.next = nil, 6
	if v, _ := c.get("a", l.pass, total); v != 6 || l.calls[len(l.calls)-1] {
		t.Fatalf("after a failure the next read must be full, not the old value: %d %v", v, l.calls)
	}
}
