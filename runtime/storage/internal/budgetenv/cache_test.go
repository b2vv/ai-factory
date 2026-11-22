package budgetenv

import (
	"errors"
	"testing"
	"time"
)

func TestCachedSizeReusesOnlyUnchangedFreshInventory(t *testing.T) {
	now := time.Unix(1000, 0)
	clock = func() time.Time { return now }
	defer func() { clock = time.Now }()
	var c cachedSize
	calls := 0
	compute := func(v int64) func() (int64, error) {
		return func() (int64, error) { calls++; return v, nil }
	}
	if v, _ := c.get("a", compute(10)); v != 10 || calls != 1 {
		t.Fatalf("first read: %d calls=%d", v, calls)
	}
	now = now.Add(sampleMaxAge - time.Second)
	if v, _ := c.get("a", compute(99)); v != 10 || calls != 1 {
		t.Fatalf("unchanged token must reuse: %d calls=%d", v, calls)
	}
	if v, _ := c.get("b", compute(11)); v != 11 || calls != 2 {
		t.Fatalf("changed token must recompute: %d calls=%d", v, calls)
	}
	now = now.Add(sampleMaxAge)
	if v, _ := c.get("b", compute(12)); v != 12 || calls != 3 {
		t.Fatalf("expired value must recompute: %d calls=%d", v, calls)
	}
	now = now.Add(-time.Hour)
	if v, _ := c.get("b", compute(13)); v != 13 || calls != 4 {
		t.Fatalf("clock moving back must recompute: %d calls=%d", v, calls)
	}
}

func TestCachedSizeNeverKeepsAFailedInventory(t *testing.T) {
	clock = func() time.Time { return time.Unix(1000, 0) }
	defer func() { clock = time.Now }()
	var c cachedSize
	if _, err := c.get("a", func() (int64, error) { return 5, nil }); err != nil {
		t.Fatal(err)
	}
	boom := errors.New("backend down")
	if _, err := c.get("b", func() (int64, error) { return 0, boom }); !errors.Is(err, boom) {
		t.Fatalf("error must surface: %v", err)
	}
	calls := 0
	if v, _ := c.get("a", func() (int64, error) { calls++; return 6, nil }); v != 6 || calls != 1 {
		t.Fatalf("after a failure the old value must not return: %d calls=%d", v, calls)
	}
}
