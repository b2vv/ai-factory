package api

import (
	"aifactory.local/storage/internal/archive"
	"crypto/sha256"
	"encoding/hex"
	"fmt"
	"sync"
	"time"
)

const maxAttempts = 10000
const attemptTTL = 10 * time.Minute

type attemptObservation struct {
	active  int
	state   string
	expires time.Time
}
type attemptBook struct {
	mu    sync.Mutex
	items map[string]attemptObservation
}

func attemptKey(key string) string { h := sha256.Sum256([]byte(key)); return hex.EncodeToString(h[:]) }

// Only bounded hashed identity observations are held before durable acceptance.
// They are not ACKs, WAL records or recovery authority and expire on restart/TTL.
// A proved durable/source state always takes precedence, including ambiguous errors.
func (b *attemptBook) begin(records []archive.Record) ([]string, func(string), error) {
	b.mu.Lock()
	defer b.mu.Unlock()
	now := time.Now()
	if b.items == nil {
		b.items = map[string]attemptObservation{}
	}
	for key, item := range b.items {
		if item.active == 0 && now.After(item.expires) {
			delete(b.items, key)
		}
	}
	keys := []string{}
	unique := map[string]bool{}
	needed := 0
	for _, r := range records {
		key := archive.IdentityKey(r)
		h := attemptKey(key)
		if unique[h] {
			continue
		}
		unique[h] = true
		keys = append(keys, key)
		if _, ok := b.items[h]; !ok {
			needed++
		}
	}
	if needed > maxAttempts-len(b.items) {
		return nil, nil, fmt.Errorf("ingest request observation capacity reached; retry later")
	}
	for h := range unique {
		item := b.items[h]
		item.active++
		item.state = "pending"
		item.expires = now.Add(attemptTTL)
		b.items[h] = item
	}
	finish := func(state string) {
		b.mu.Lock()
		defer b.mu.Unlock()
		for h := range unique {
			item, ok := b.items[h]
			if !ok {
				continue
			}
			item.active--
			if item.active == 0 && state == "complete" {
				delete(b.items, h)
				continue
			}
			item.state = state
			item.expires = time.Now().Add(attemptTTL)
			b.items[h] = item
		}
	}
	return keys, finish, nil
}
func (b *attemptBook) state(key string) string {
	b.mu.Lock()
	defer b.mu.Unlock()
	h := attemptKey(key)
	item, ok := b.items[h]
	if !ok {
		return ""
	}
	if item.active > 0 {
		return "pending"
	}
	if time.Now().After(item.expires) {
		delete(b.items, h)
		return ""
	}
	return item.state
}
