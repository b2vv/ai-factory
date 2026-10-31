// Package budget owns accounting, never grants, consent or storage authority.
// Metric logical-v1 counts application representations, not DB allocator pages.
package budget

import (
	"bytes"
	"crypto/sha256"
	"encoding/binary"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"sync"
	"syscall"
)

const Version = 1
const SlotBytes = 16384
const FileBytes = 2 * SlotBytes
const MaxComponents = 32
const MaxPending = 16

var ErrBlocked = errors.New("budget: unresolved or corrupt accounting; preserve state and reconcile")
var ErrCapacity = errors.New("budget: logical live budget or physical headroom unavailable")

type Policy struct{ LiveCap, Headroom, WALCap int64 }
type Evidence struct{ Kind, KeyHash, PayloadHash string }
type Intent struct {
	Evidence Evidence
	Bytes    int64
}
type State struct {
	Version    int
	Policy     Policy
	Components map[string]int64
	Pending    []Intent
}
type Sample struct {
	// Only supplied components are refreshed. Unavailable/unbound components retain
	// their last durable charge; absence NEVER means zero or permission to refund.
	Components map[string]int64
	Free       int64
}
type Sampler func() (Sample, error)
type Ledger struct {
	mu         sync.Mutex
	file       *os.File
	path       string
	generation uint64
	state      State
	sample     Sampler
	poisoned   bool
}

// Open acquires an accounting-specific nonblocking lock in addition to the
// enclosing control-state ownership fence. It never creates or resets state.
func Open(path string, sample Sampler) (*Ledger, error) {
	fd, e := syscall.Open(path, syscall.O_RDWR|syscall.O_NOFOLLOW, 0600)
	if e != nil {
		return nil, e
	}
	f := os.NewFile(uintptr(fd), path)
	fail := func(e error) (*Ledger, error) { f.Close(); return nil, e }
	if e = syscall.Flock(fd, syscall.LOCK_EX|syscall.LOCK_NB); e != nil {
		return fail(fmt.Errorf("budget: accounting owner busy: %w", e))
	}
	st, e := f.Stat()
	if e != nil || !st.Mode().IsRegular() || st.Size() != FileBytes {
		return fail(ErrBlocked)
	}
	raw := make([]byte, FileBytes)
	if _, e = f.ReadAt(raw, 0); e != nil {
		return fail(ErrBlocked)
	}
	a, ga, e := decode(raw[:SlotBytes])
	if e != nil {
		return fail(e)
	}
	b, gb, e := decode(raw[SlotBytes:])
	if e != nil {
		return fail(e)
	}
	if ga == gb {
		if !bytes.Equal(raw[:SlotBytes], raw[SlotBytes:]) {
			return fail(ErrBlocked)
		}
	} else if ga > gb {
		if ga-gb != 1 {
			return fail(ErrBlocked)
		}
	} else if gb-ga != 1 {
		return fail(ErrBlocked)
	}
	state, g := a, ga
	if gb > ga {
		state, g = b, gb
	}
	return &Ledger{file: f, path: path, generation: g, state: state, sample: sample}, nil
}

// Initialize is explicit and exclusive. Existing or partially written ledgers
// refuse; a failed creation is retained as evidence, never auto-reset.
func Initialize(path string, policy Policy, sample Sampler) (*Ledger, error) {
	if policy.LiveCap < FileBytes || policy.Headroom < 0 || sample == nil {
		return nil, ErrCapacity
	}
	snap, e := sample()
	if e != nil {
		return nil, e
	}
	if _, e = os.Lstat(path); !os.IsNotExist(e) {
		return nil, fmt.Errorf("budget: existing accounting requires Open")
	}
	used, e := sum(snap.Components)
	if e != nil {
		return nil, e
	}
	if used > policy.LiveCap-FileBytes || snap.Free < policy.Headroom || FileBytes > snap.Free-policy.Headroom {
		return nil, ErrCapacity
	}
	state := State{Version: Version, Policy: policy, Components: clone(snap.Components)}
	// The fixed, fully reserved two-slot accounting file is always itself billed.
	state.Components["budget-ledger"] = FileBytes
	raw, e := encode(state, 0)
	if e != nil {
		return nil, e
	}
	fd, e := syscall.Open(path, syscall.O_RDWR|syscall.O_CREAT|syscall.O_EXCL|syscall.O_NOFOLLOW, 0600)
	if e != nil {
		return nil, e
	}
	f := os.NewFile(uintptr(fd), path)
	if e = syscall.Flock(fd, syscall.LOCK_EX|syscall.LOCK_NB); e != nil {
		f.Close()
		return nil, e
	}
	if _, e = f.Write(append(raw, raw...)); e == nil {
		e = f.Sync()
	}
	if e == nil {
		e = syncDir(filepath.Dir(path))
	}
	if e != nil {
		f.Close()
		return nil, e
	}
	return &Ledger{file: f, path: path, state: state, sample: sample}, nil
}
func (l *Ledger) Close() error         { l.mu.Lock(); defer l.mu.Unlock(); return l.file.Close() }
func (l *Ledger) SetSampler(s Sampler) { l.mu.Lock(); defer l.mu.Unlock(); l.sample = s }
func (l *Ledger) Snapshot() State {
	l.mu.Lock()
	defer l.mu.Unlock()
	s := l.state
	s.Components = clone(s.Components)
	s.Pending = append([]Intent(nil), s.Pending...)
	return s
}
func (l *Ledger) Configure(p Policy) error {
	l.mu.Lock()
	defer l.mu.Unlock()
	if l.poisoned || len(l.state.Pending) > 0 {
		return ErrBlocked
	}
	if p.LiveCap < FileBytes || p.Headroom < 0 {
		return ErrCapacity
	}
	next := l.copyState()
	next.Policy = p
	used, e := sum(next.Components)
	if e != nil || used > p.LiveCap {
		return ErrCapacity
	}
	return l.persist(next)
}

// Reserve persists the complete liability before a writer is allowed to mutate.
// Callers hold their enclosing write/authority fence through Finish. Pending
// intents from a prior failure cannot be overwritten or silently remeasured away.
func (l *Ledger) Reserve(evidence Evidence, growth int64) error {
	l.mu.Lock()
	defer l.mu.Unlock()
	if l.poisoned || len(l.state.Pending) > 0 {
		return ErrBlocked
	}
	if growth < 0 || evidence.Kind == "" {
		return ErrCapacity
	}
	next, snap, e := l.refreshed()
	if e != nil {
		return e
	}
	used, e := sum(next.Components)
	if e != nil {
		return e
	}
	p := next.Policy
	if used > p.LiveCap || growth > p.LiveCap-used || snap.Free < p.Headroom || growth > snap.Free-p.Headroom {
		return ErrCapacity
	}
	next.Pending = []Intent{{Evidence: evidence, Bytes: growth}}
	return l.persist(next)
}

// Finish is called only after the operation's durable success has been verified.
// A measurement or persistence failure retains the intent and refuses new writes.
func (l *Ledger) Finish() error {
	l.mu.Lock()
	defer l.mu.Unlock()
	if l.poisoned {
		return ErrBlocked
	}
	if len(l.state.Pending) == 0 {
		return nil
	}
	next, _, e := l.refreshed()
	if e != nil {
		return e
	}
	used, e := sum(next.Components)
	if e != nil || used > next.Policy.LiveCap {
		return ErrCapacity
	}
	next.Pending = nil
	return l.persist(next)
}

// Recover requires independent positive proof for EVERY intent. The verifier may
// inspect existing durable journal/DB evidence but may not infer success from an
// absent accept marker or from a smaller usage sample. Unknown outcomes stay held.
func (l *Ledger) Recover(prove func(Intent) (bool, error)) error {
	l.mu.Lock()
	defer l.mu.Unlock()
	if l.poisoned {
		return ErrBlocked
	}
	if len(l.state.Pending) == 0 {
		return nil
	}
	for _, intent := range l.state.Pending {
		ok, e := prove(intent)
		if e != nil {
			return e
		}
		if !ok {
			return ErrBlocked
		}
	}
	next, _, e := l.refreshed()
	if e != nil {
		return e
	}
	used, e := sum(next.Components)
	if e != nil || used > next.Policy.LiveCap {
		return ErrCapacity
	}
	next.Pending = nil
	return l.persist(next)
}
func (l *Ledger) Refresh() error {
	l.mu.Lock()
	defer l.mu.Unlock()
	if l.poisoned || len(l.state.Pending) > 0 {
		return ErrBlocked
	}
	next, _, e := l.refreshed()
	if e != nil {
		return e
	}
	used, e := sum(next.Components)
	if e != nil || used > next.Policy.LiveCap {
		return ErrCapacity
	}
	return l.persist(next)
}
func (l *Ledger) copyState() State {
	s := l.state
	s.Components = clone(s.Components)
	s.Pending = append([]Intent(nil), s.Pending...)
	return s
}
func (l *Ledger) refreshed() (State, Sample, error) {
	if l.sample == nil {
		return State{}, Sample{}, ErrBlocked
	}
	snap, e := l.sample()
	if e != nil {
		return State{}, Sample{}, e
	}
	next := l.copyState()
	for key, value := range snap.Components {
		if key == "" || len(key) > 160 || value < 0 {
			return State{}, Sample{}, ErrBlocked
		}
		next.Components[key] = value
	}
	next.Components["budget-ledger"] = FileBytes
	if len(next.Components) > MaxComponents || snap.Free < 0 {
		return State{}, Sample{}, ErrBlocked
	}
	return next, snap, nil
}
func (l *Ledger) persist(next State) error {
	if l.generation == ^uint64(0) {
		return ErrBlocked
	}
	generation := l.generation + 1
	raw, e := encode(next, generation)
	if e != nil {
		return e
	}
	n, e := l.file.WriteAt(raw, int64(generation%2)*SlotBytes)
	if e == nil && n != len(raw) {
		e = io.ErrShortWrite
	}
	if e == nil {
		e = l.file.Sync()
	}
	if e != nil {
		l.poisoned = true
		return fmt.Errorf("%w: accounting write uncertain: %v", ErrBlocked, e)
	}
	l.state = next
	l.generation = generation
	return nil
}
func encode(state State, generation uint64) ([]byte, error) {
	if e := validate(state); e != nil {
		return nil, e
	}
	payload, e := json.Marshal(state)
	if e != nil || len(payload) > SlotBytes-52 {
		return nil, ErrBlocked
	}
	raw := make([]byte, SlotBytes)
	copy(raw, []byte("AIFBGT1\n"))
	binary.BigEndian.PutUint64(raw[8:16], generation)
	binary.BigEndian.PutUint32(raw[16:20], uint32(len(payload)))
	copy(raw[20:], payload)
	hash := sha256.Sum256(raw[:SlotBytes-32])
	copy(raw[SlotBytes-32:], hash[:])
	return raw, nil
}
func decode(raw []byte) (State, uint64, error) {
	var state State
	if len(raw) != SlotBytes || string(raw[:8]) != "AIFBGT1\n" {
		return state, 0, ErrBlocked
	}
	hash := sha256.Sum256(raw[:SlotBytes-32])
	if !bytes.Equal(hash[:], raw[SlotBytes-32:]) {
		return state, 0, ErrBlocked
	}
	n := int(binary.BigEndian.Uint32(raw[16:20]))
	if n > SlotBytes-52 {
		return state, 0, ErrBlocked
	}
	decoder := json.NewDecoder(bytes.NewReader(raw[20 : 20+n]))
	decoder.DisallowUnknownFields()
	if e := decoder.Decode(&state); e != nil {
		return state, 0, ErrBlocked
	}
	for _, v := range raw[20+n : SlotBytes-32] {
		if v != 0 {
			return state, 0, ErrBlocked
		}
	}
	if e := validate(state); e != nil {
		return state, 0, e
	}
	return state, binary.BigEndian.Uint64(raw[8:16]), nil
}
func validate(s State) error {
	if s.Version != Version || s.Policy.LiveCap < FileBytes || s.Policy.Headroom < 0 || s.Components == nil || s.Components["budget-ledger"] != FileBytes || len(s.Components) > MaxComponents || len(s.Pending) > MaxPending {
		return ErrBlocked
	}
	if _, e := sum(s.Components); e != nil {
		return e
	}
	for _, p := range s.Pending {
		if p.Bytes < 0 || p.Evidence.Kind == "" || len(p.Evidence.Kind) > 64 || len(p.Evidence.KeyHash) > 64 || len(p.Evidence.PayloadHash) > 64 {
			return ErrBlocked
		}
	}
	return nil
}
func sum(values map[string]int64) (int64, error) {
	var total int64
	for key, v := range values {
		if key == "" || len(key) > 160 || v < 0 || v > int64(^uint64(0)>>1)-total {
			return 0, ErrBlocked
		}
		total += v
	}
	return total, nil
}
func clone(values map[string]int64) map[string]int64 {
	out := map[string]int64{}
	for k, v := range values {
		out[k] = v
	}
	return out
}
func syncDir(path string) error {
	f, e := os.Open(path)
	if e != nil {
		return e
	}
	defer f.Close()
	return f.Sync()
}

// Resume permits only the exact idempotent operation represented by a surviving
// intent. It never reserves a second operation or refunds the original liability.
// The enclosing owner must prove the operation's identity and serialize retries.
func (l *Ledger) Resume(evidence Evidence) error {
	l.mu.Lock()
	defer l.mu.Unlock()
	if l.poisoned || len(l.state.Pending) != 1 || l.state.Pending[0].Evidence != evidence {
		return ErrBlocked
	}
	_, _, e := l.refreshed()
	return e
}
