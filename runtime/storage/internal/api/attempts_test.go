package api

import (
	"aifactory.local/storage/internal/archive"
	"testing"
	"time"
)

func TestAttemptBookBoundedConcurrentIdentityAndExpiry(t *testing.T) {
	var b attemptBook
	r := archive.Record{Project: "p", MessageID: "m"}
	key := archive.IdentityKey(r)
	_, done, e := b.begin([]archive.Record{r, r})
	if e != nil {
		t.Fatal(e)
	}
	_, second, e := b.begin([]archive.Record{r})
	if e != nil {
		t.Fatal(e)
	}
	done("failed")
	if got := b.state(key); got != "pending" {
		t.Fatal(got)
	}
	second("cancelled")
	if got := b.state(key); got != "cancelled" {
		t.Fatal(got)
	}
	h := attemptKey(key)
	v := b.items[h]
	v.expires = time.Now().Add(-time.Second)
	b.items[h] = v
	if got := b.state(key); got != "" {
		t.Fatal("expired outcome", got)
	}
	for n := 0; n < maxAttempts; n++ {
		b.items[time.Unix(int64(n), 0).String()] = attemptObservation{active: 1}
	}
	if _, _, e = b.begin([]archive.Record{r}); e == nil {
		t.Fatal("unbounded observations")
	}
}
