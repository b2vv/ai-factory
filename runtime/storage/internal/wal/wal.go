// Package wal is the durable intake journal (PLAN v4 §6). It implements:
//   - reserve-before-accept with THREE durable boundaries — an intent/reservation
//     fsync, a frame fsync, then an accept-entry fsync — so recovery has independent
//     evidence of what a crash was in the middle of writing;
//   - bounded capacity enforced by rejecting intake, NEVER evicting accepted data;
//   - idempotency/dedup keyed by the EXACT idempotency key (never a 32-bit hash), with
//     a durable exact-key index that survives compaction;
//   - crash/corrupt-tail recovery under the V3-1 rule: a missing/invalid acceptance
//     marker is AMBIGUOUS, not proof of non-acceptance. Recovery NEVER silently
//     truncates a region it cannot prove was unaccepted. A frame that fills its
//     reserved span but lacks a valid accept is ambiguous and BLOCKED; a frame that is
//     physically shorter than its reserved span and lacks a valid accept is EQUALLY
//     ambiguous — an interrupted append and an accepted frame whose data was later
//     truncated (and whose marker was removed) are indistinguishable from the journal
//     alone — so it too is BLOCKED (preserve + operator resolution), never truncated.
//     Accepted data is never silently discarded.
//
// Why reservations: the accepts file can be independently truncated or an in-frame
// length field can be flipped. Neither an empty/shorter-but-CRC-valid accepts chain
// nor a frame whose declared length overruns the file is positive proof of
// non-acceptance. The reservation records the authoritative frame span (offset+length)
// BEFORE the frame is written and carries its own integrity CRC, so corrupt reservation
// metadata (a flipped offset/length) is detected rather than trusted. Because a short
// data file with a missing marker is itself ambiguous, recovery preserves and BLOCKS
// such tails rather than deleting possibly-accepted bytes; only an explicit operator
// disposition may discard them.
//
// On-disk layout (WAL dir):
//
//	intents: fixed 33-byte reservations [ 'R' | seq u64 | frameOff u64 | frameLen u64 | frameCRC u32 | recCRC u32 ]
//	data:    frames [ 'F' | seq u64 | keyLen u32 | payLen u32 | key | payload | crc u32 ]
//	accepts: fixed 29-byte CRC-chained commits [ 'A' | seq u64 | frameOff u64 | frameCRC u32 | keyHash u32 | chainCRC u32 ]
//	committed.idx: exact-key dedup index [ keyLen u32 | seq u64 | key | recCRC u32 ] (survives compaction; reconciled against the journal)
//
// Order per record: reserve(fsync) -> frame(fsync) -> accept(fsync) -> committed.idx -> ack.
package wal

import (
	"encoding/binary"
	"errors"
	"fmt"
	"hash/crc32"
	"os"
	"path/filepath"
)

const (
	frameMagic  = 'F'
	acceptMagic = 'A'
	intentMagic = 'R'
	acceptSize  = 1 + 8 + 8 + 4 + 4 + 4 // 29 bytes, fixed
	intentBody  = 1 + 8 + 8 + 8 + 4     // 29 bytes covered by the reservation's integrity CRC
	intentSize  = intentBody + 4        // 33 bytes, fixed (body + recCRC)
)

var crcTab = crc32.IEEETable

// syncDir fsyncs a directory so that newly created entries within it are durable. It is a
// package var so a focused test can inject a deterministic fault (this exercises failure
// PROPAGATION; it is NOT a substitute for physical power-loss verification, which these
// tests cannot perform).
var syncDir = func(dir string) error {
	f, err := os.Open(dir)
	if err != nil {
		return err
	}
	defer f.Close()
	return f.Sync()
}

// Receipt is returned to the producer once a record is durable-accepted.
type Receipt struct {
	Seq       uint64
	Key       string // stable idempotency key
	Duplicate bool   // true if this key was already accepted (no new frame written)
}

// WAL is the append-only journal. Not safe for concurrent writers by design: the
// API is the single journal writer (PLAN §6.2); callers serialize.
type WAL struct {
	dir        string
	data       *os.File
	intents    *os.File
	accepts    *os.File
	seq        uint64
	chainCRC   uint32
	dedup      map[string]uint64 // EXACT key -> seq; rebuilt from authoritative records on Open
	appendable bool              // false until a clean/applied recovery; blocks appends after ambiguity
}

// Open creates/opens a WAL in dir and restores authoritative state (sequence, accept
// chain, exact-key dedup) from the validated journal. If recovery is clean the WAL is
// immediately appendable; if a truncation is pending or the journal is ambiguous, the
// caller MUST run RecoverPlan+Apply before appending.
func Open(dir string) (*WAL, error) {
	if err := os.MkdirAll(dir, 0o700); err != nil {
		return nil, err
	}
	d, err := os.OpenFile(filepath.Join(dir, "data"), os.O_CREATE|os.O_RDWR|os.O_APPEND, 0o600)
	if err != nil {
		return nil, err
	}
	in, err := os.OpenFile(filepath.Join(dir, "intents"), os.O_CREATE|os.O_RDWR|os.O_APPEND, 0o600)
	if err != nil {
		d.Close()
		return nil, err
	}
	a, err := os.OpenFile(filepath.Join(dir, "accepts"), os.O_CREATE|os.O_RDWR|os.O_APPEND, 0o600)
	if err != nil {
		d.Close()
		in.Close()
		return nil, err
	}
	w := &WAL{dir: dir, data: d, intents: in, accepts: a, dedup: map[string]uint64{}}

	// C: a newly CREATED file's directory entry is not durable until the directory itself
	// is fsync'd; a crash after creating "data"/"intents"/"accepts" but before the parent
	// directory is synced could lose the files entirely. Create the dedup index eagerly too
	// so its directory entry is covered by the SAME single directory fsync (appendCommitted
	// then only appends to an existing inode and needs no further directory sync). Any
	// fsync failure is PROPAGATED, never swallowed.
	ci, err := os.OpenFile(filepath.Join(dir, "committed.idx"), os.O_CREATE|os.O_RDWR|os.O_APPEND, 0o600)
	if err != nil {
		w.Close()
		return nil, err
	}
	ci.Close()
	if err := syncDir(dir); err != nil {
		w.Close()
		return nil, fmt.Errorf("wal: fsync of journal directory failed (journal files may not be durable): %w", err)
	}

	rep, err := RecoverPlan(dir)
	if err != nil {
		w.Close()
		return nil, err
	}
	// Restore in-memory authority from the validated prefix.
	w.seq = rep.seq
	w.chainCRC = rep.chain
	for k, s := range rep.dedup {
		w.dedup[k] = s
	}
	// Fold in the durable exact-key dedup index, reconciled against the authoritative
	// journal (survives compaction; never manufactures acceptance the journal denies).
	foldCommitted(dir, w.dedup, rep.seqKeys)
	// Appendable only when recovery is clean (no blocked regions, no pending truncation).
	w.appendable = !rep.IsBlocked() && rep.TruncateAt < 0
	return w, nil
}

func (w *WAL) Close() error {
	var first error
	for _, f := range []*os.File{w.data, w.intents, w.accepts} {
		if f == nil {
			continue
		}
		if err := f.Close(); err != nil && first == nil {
			first = err
		}
	}
	return first
}

func frameBytes(seq uint64, key, payload []byte) []byte {
	b := make([]byte, 0, 1+8+4+4+len(key)+len(payload)+4)
	b = append(b, frameMagic)
	b = binary.BigEndian.AppendUint64(b, seq)
	b = binary.BigEndian.AppendUint32(b, uint32(len(key)))
	b = binary.BigEndian.AppendUint32(b, uint32(len(payload)))
	b = append(b, key...)
	b = append(b, payload...)
	body := b[1:] // seq..payload
	b = binary.BigEndian.AppendUint32(b, crc32.Checksum(body, crcTab))
	return b
}

// Accept writes a reservation, a frame, then a durable accept entry and returns a
// Receipt. If the EXACT key was already accepted it is a no-op returning
// Duplicate=true (F7 dedup). The caller MUST have performed admission
// (config.Accountant) before calling Accept.
func (w *WAL) Accept(key string, payload []byte) (Receipt, error) {
	if key == "" {
		return Receipt{}, errors.New("wal: empty idempotency key")
	}
	if !w.appendable {
		return Receipt{}, errors.New("wal: not appendable; recovery required (ambiguous/blocked journal or unapplied truncation)")
	}
	// Exact-key dedup. The dedup map is rebuilt from authoritative records on Open and
	// from the durable exact-key index, so a replayed delivery is recognized across
	// restarts and (eventually) across compaction — without 32-bit hash collisions.
	if seq, ok := w.dedup[key]; ok {
		return Receipt{Seq: seq, Key: key, Duplicate: true}, nil
	}

	off, err := w.data.Seek(0, 2)
	if err != nil {
		return Receipt{}, err
	}
	fb := frameBytes(w.seq+1, []byte(key), payload)
	frameCRC := crc32.Checksum(fb[1:len(fb)-4], crcTab)
	seq := w.seq + 1

	// 1) Reserve: record the authoritative frame span BEFORE writing the frame, so
	//    recovery can tell an interrupted append from a fully-written-then-damaged
	//    frame regardless of the corruptible in-frame length field.
	res := intentBytes(seq, uint64(off), uint64(len(fb)), frameCRC)
	if _, err := w.intents.Write(res); err != nil {
		return Receipt{}, err
	}
	if err := w.intents.Sync(); err != nil {
		return Receipt{}, err
	}

	// 2) Append + fsync the full frame. A crash here leaves the reserved span only
	//    partially written = positively unaccepted (no accept entry). A write/sync
	//    failure past the durable reservation leaves the journal needing recovery, so
	//    we quarantine further appends until RecoverPlan+Apply repairs it.
	if _, err := w.data.Write(fb); err != nil {
		w.appendable = false
		return Receipt{}, err
	}
	if err := w.data.Sync(); err != nil {
		w.appendable = false
		return Receipt{}, err
	}

	// 3) Append + fsync the accept entry. Only after this is the record acknowledged.
	keyHash := crc32.Checksum([]byte(key), crcTab)
	entry := w.acceptEntry(seq, uint64(off), frameCRC, keyHash)
	if _, err := w.accepts.Write(entry); err != nil {
		w.appendable = false
		return Receipt{}, err
	}
	if err := w.accepts.Sync(); err != nil {
		w.appendable = false
		return Receipt{}, err
	}
	// Durable acceptance has happened. Update in-memory authority first so any retry
	// (including after a committed-index failure below) is deduplicated.
	w.seq = seq
	w.chainCRC = acceptChain(w.chainCRC, seq, uint64(off), frameCRC, keyHash)
	w.dedup[key] = seq

	// 4) Persist the exact key to the compaction-surviving dedup index. A failure here
	//    does NOT un-accept the record (frame+accept are durable and will replay/rebuild
	//    dedup on restart); we propagate it rather than silently dropping it.
	if err := w.appendCommitted(key, seq); err != nil {
		return Receipt{Seq: seq, Key: key}, fmt.Errorf("wal: record accepted (seq %d) but dedup index persist failed: %w", seq, err)
	}
	return Receipt{Seq: seq, Key: key}, nil
}

func intentBytes(seq, frameOff, frameLen uint64, frameCRC uint32) []byte {
	b := make([]byte, 0, intentSize)
	b = append(b, intentMagic)
	b = binary.BigEndian.AppendUint64(b, seq)
	b = binary.BigEndian.AppendUint64(b, frameOff)
	b = binary.BigEndian.AppendUint64(b, frameLen)
	b = binary.BigEndian.AppendUint32(b, frameCRC)
	// Integrity CRC over the reservation body so a flipped offset/length/seq is detected
	// at recovery instead of being trusted (it is NOT proof of a short interrupted tail).
	b = binary.BigEndian.AppendUint32(b, crc32.Checksum(b, crcTab))
	return b
}

// checkedAdd returns a+b and false on unsigned overflow, so recovery never computes an
// out-of-range span from corrupt reservation metadata.
func checkedAdd(a, b uint64) (uint64, bool) {
	s := a + b
	if s < a {
		return 0, false
	}
	return s, true
}

func (w *WAL) acceptEntry(seq, frameOff uint64, frameCRC, keyHash uint32) []byte {
	b := make([]byte, 0, acceptSize)
	b = append(b, acceptMagic)
	b = binary.BigEndian.AppendUint64(b, seq)
	b = binary.BigEndian.AppendUint64(b, frameOff)
	b = binary.BigEndian.AppendUint32(b, frameCRC)
	b = binary.BigEndian.AppendUint32(b, keyHash)
	chain := acceptChain(w.chainCRC, seq, frameOff, frameCRC, keyHash)
	b = binary.BigEndian.AppendUint32(b, chain)
	return b
}

func acceptChain(prev uint32, seq, frameOff uint64, frameCRC, keyHash uint32) uint32 {
	buf := make([]byte, 0, 4+8+8+4+4)
	buf = binary.BigEndian.AppendUint32(buf, prev)
	buf = binary.BigEndian.AppendUint64(buf, seq)
	buf = binary.BigEndian.AppendUint64(buf, frameOff)
	buf = binary.BigEndian.AppendUint32(buf, frameCRC)
	buf = binary.BigEndian.AppendUint32(buf, keyHash)
	return crc32.Checksum(buf, crcTab)
}

// committed index (exact-key dedup, survives compaction) ----------------------

func (w *WAL) appendCommitted(key string, seq uint64) error {
	f, err := os.OpenFile(filepath.Join(w.dir, "committed.idx"), os.O_CREATE|os.O_WRONLY|os.O_APPEND, 0o600)
	if err != nil {
		return err
	}
	rec := make([]byte, 0, 4+8+len(key)+4)
	rec = binary.BigEndian.AppendUint32(rec, uint32(len(key)))
	rec = binary.BigEndian.AppendUint64(rec, seq)
	rec = append(rec, key...)
	rec = binary.BigEndian.AppendUint32(rec, crc32.Checksum(rec, crcTab))
	if _, err := f.Write(rec); err != nil {
		f.Close()
		return err
	}
	if err := f.Sync(); err != nil {
		f.Close()
		return err
	}
	return f.Close()
}

// loadCommitted returns the exact keys recorded in the durable dedup index whose
// per-record integrity CRC validates. A missing index is not evidence of anything and
// yields an empty set; a truncated or corrupt trailing record stops parsing (the
// authoritative accepts/data rebuild still covers live records). The returned keys are
// NOT authoritative on their own — foldCommitted reconciles them against the journal.
func loadCommitted(dir string) map[string]uint64 {
	keys := map[string]uint64{}
	b, err := os.ReadFile(filepath.Join(dir, "committed.idx"))
	if err != nil {
		return keys
	}
	for i := 0; i+12 <= len(b); {
		keyLen := int(binary.BigEndian.Uint32(b[i : i+4]))
		seq := binary.BigEndian.Uint64(b[i+4 : i+12])
		start := i + 12
		end := start + keyLen
		if keyLen < 0 || end < start || end+4 > len(b) {
			break // truncated/partial trailing record
		}
		rec := b[i : end+4]
		if crc32.Checksum(rec[:len(rec)-4], crcTab) != binary.BigEndian.Uint32(rec[len(rec)-4:]) {
			break // corrupt record: stop trusting the remainder of the index
		}
		keys[string(b[start:end])] = seq
		i = end + 4
	}
	return keys
}

// foldCommitted folds the durable exact-key index into dedup, but ONLY where it is
// consistent with the authoritative journal: an entry whose sequence is not among the
// validated journal records, or whose key contradicts the record at that sequence, is
// rejected. A secondary cache must never manufacture an acceptance the source records
// do not contain (compaction that legitimately removes source records requires a
// verified durable barrier, which is future work; until then the journal is authority).
func foldCommitted(dir string, dedup map[string]uint64, seqKeys map[uint64]string) {
	for k, s := range loadCommitted(dir) {
		jk, ok := seqKeys[s]
		if !ok || jk != k {
			continue // unknown sequence or contradicts the journal: reject
		}
		if _, exists := dedup[k]; !exists {
			dedup[k] = s
		}
	}
}

// Recovery --------------------------------------------------------------------

// Disposition classifies a parsed region of the WAL at recovery.
type Disposition string

const (
	Replay   Disposition = "replay"   // complete frame with a matching valid accept entry
	Truncate Disposition = "truncate" // trailing incomplete frame: POSITIVELY unaccepted
	Blocked  Disposition = "blocked"  // ambiguous/damaged: preserve + recovery BLOCKED
)

// Diagnostic is an actionable recovery finding.
type Diagnostic struct {
	Offset int64
	Seq    uint64
	Key    string
	Reason string
}

// Report is the outcome of RecoverPlan. Truncation is applied ONLY when IsBlocked() is
// false and TruncateAt >= 0.
type Report struct {
	Replay     []Diagnostic
	TruncateAt int64        // byte offset in data where a provably-unaccepted tail begins; -1 if none
	BlockedDx  []Diagnostic // ambiguous/damaged; recovery is BLOCKED if non-empty

	// restore state (validated prefix), used by Apply to rebuild authority.
	seq            uint64
	chain          uint32
	dedup          map[string]uint64
	seqKeys        map[uint64]string // validated journal sequence -> exact key, used to reconcile the dedup index
	truncIntentsAt int64             // intents byte offset to truncate to when a tail frame is dropped; -1 if none
}

func (r Report) IsBlocked() bool { return len(r.BlockedDx) > 0 }

type reservation struct {
	seq        uint64
	off        uint64
	frameLen   uint64
	frameCRC   uint32
	intentsOff uint64
}

type acceptRec struct {
	seq      uint64
	frameCRC uint32
	keyHash  uint32
}

type frame struct {
	seq uint64
	key string
	crc uint32
}

// RecoverPlan parses the intents, accepts and data files and classifies the journal
// under the V3-1 rule. It mutates nothing.
func RecoverPlan(dir string) (Report, error) {
	intentsB, err := os.ReadFile(filepath.Join(dir, "intents"))
	if err != nil {
		return Report{}, err
	}
	data, err := os.ReadFile(filepath.Join(dir, "data"))
	if err != nil {
		return Report{}, err
	}
	accB, err := os.ReadFile(filepath.Join(dir, "accepts"))
	if err != nil {
		return Report{}, err
	}

	rep := Report{TruncateAt: -1, dedup: map[string]uint64{}, seqKeys: map[uint64]string{}, truncIntentsAt: -1}

	// Parse reservations in order, validating each record's integrity CRC and requiring
	// strictly increasing sequence and non-overlapping, ordered data spans. A corrupt,
	// partial or out-of-order record means the metadata inventory is damaged; we stop
	// and mark the tail damaged (it is NOT a clean truncatable boundary).
	var reservations []reservation
	intentsTailDamaged := false
	ii := 0
	for ; ii+intentSize <= len(intentsB); ii += intentSize {
		e := intentsB[ii : ii+intentSize]
		if e[0] != intentMagic {
			intentsTailDamaged = true
			break
		}
		if crc32.Checksum(e[:intentBody], crcTab) != binary.BigEndian.Uint32(e[intentBody:intentSize]) {
			intentsTailDamaged = true // flipped offset/length/seq: do not trust it
			break
		}
		r := reservation{
			seq:        binary.BigEndian.Uint64(e[1:9]),
			off:        binary.BigEndian.Uint64(e[9:17]),
			frameLen:   binary.BigEndian.Uint64(e[17:25]),
			frameCRC:   binary.BigEndian.Uint32(e[25:29]),
			intentsOff: uint64(ii),
		}
		if n := len(reservations); n > 0 {
			prev := reservations[n-1]
			prevEnd, ok := checkedAdd(prev.off, prev.frameLen)
			if r.seq <= prev.seq || !ok || r.off < prevEnd {
				intentsTailDamaged = true
				break
			}
		}
		reservations = append(reservations, r)
	}
	if ii < len(intentsB) {
		intentsTailDamaged = true // unparsed trailing bytes after the last clean record
	}

	// Parse the accept chain, honoring the CRC chain; stop at the first break. Any
	// unparsed trailing bytes mean the accepts file is damaged and recovery must not
	// treat the journal as append-ready.
	accByOff := map[uint64]acceptRec{}
	var chain uint32
	ai := 0
	for ; ai+acceptSize <= len(accB); ai += acceptSize {
		e := accB[ai : ai+acceptSize]
		if e[0] != acceptMagic {
			break
		}
		seq := binary.BigEndian.Uint64(e[1:9])
		off := binary.BigEndian.Uint64(e[9:17])
		fcrc := binary.BigEndian.Uint32(e[17:21])
		khash := binary.BigEndian.Uint32(e[21:25])
		want := binary.BigEndian.Uint32(e[25:29])
		if acceptChain(chain, seq, off, fcrc, khash) != want {
			break
		}
		chain = want
		accByOff[off] = acceptRec{seq: seq, frameCRC: fcrc, keyHash: khash}
	}
	acceptsTailDamaged := ai < len(accB)
	rep.chain = chain // chain value after the last valid accept (unaffected by data truncation)

	validated := map[uint64]bool{}

	// Walk reservations in order. Nothing valid can follow the first incomplete,
	// ambiguous or blocked reservation, so we stop at it.
	for idx := 0; idx < len(reservations); idx++ {
		r := reservations[idx]
		spanEnd, spanOK := checkedAdd(r.off, r.frameLen)
		ar, hasAccept := accByOff[r.off]

		if !spanOK || r.off > uint64(len(data)) || spanEnd > uint64(len(data)) {
			// The reserved span is not fully present in the data file (physically short),
			// or its arithmetic overflowed (corrupt metadata). A short/missing span plus
			// a missing accept marker is NOT proof the frame was never accepted: an
			// interrupted append and an accepted frame whose data was later truncated
			// (with its marker removed) are indistinguishable from the journal alone.
			// Preserve and BLOCK; never truncate possibly-accepted bytes.
			if hasAccept {
				rep.BlockedDx = append(rep.BlockedDx, Diagnostic{
					Offset: int64(r.off), Seq: ar.seq,
					Reason: "accepted frame whose data region is missing/short (orphan accept): preserve/quarantine + BLOCKED",
				})
			} else {
				rep.BlockedDx = append(rep.BlockedDx, Diagnostic{
					Offset: int64(r.off), Seq: r.seq,
					Reason: "reserved frame shorter than its recorded span with no valid accept marker: ambiguous (interrupted append and truncated-after-acceptance are indistinguishable); preserve + BLOCKED",
				})
			}
			break
		}

		fr, ok := parseFrameSpan(data[r.off:spanEnd], r.frameCRC)
		if !ok {
			// Full reserved span present but the frame content is damaged.
			if hasAccept {
				rep.BlockedDx = append(rep.BlockedDx, Diagnostic{
					Offset: int64(r.off), Seq: ar.seq,
					Reason: "accepted frame with payload/CRC damage: preserve/quarantine + BLOCKED",
				})
			} else {
				rep.BlockedDx = append(rep.BlockedDx, Diagnostic{
					Offset: int64(r.off), Seq: r.seq,
					Reason: "fully-written reserved frame without a valid accept marker: ambiguous (may have been acknowledged then damaged); preserve + BLOCKED",
				})
			}
			break
		}

		switch {
		case hasAccept && ar.frameCRC == fr.crc:
			rep.Replay = append(rep.Replay, Diagnostic{Offset: int64(r.off), Seq: fr.seq, Key: fr.key})
			validated[r.off] = true
			rep.dedup[fr.key] = fr.seq
			rep.seqKeys[fr.seq] = fr.key
			if fr.seq > rep.seq {
				rep.seq = fr.seq
			}
		case hasAccept && ar.frameCRC != fr.crc:
			rep.BlockedDx = append(rep.BlockedDx, Diagnostic{
				Offset: int64(r.off), Seq: fr.seq, Key: fr.key,
				Reason: "accepted frame CRC mismatch (payload damaged after acceptance): preserve/quarantine + BLOCKED",
			})
			return rep, nil
		default:
			// Complete, valid frame with NO valid accept entry. Per V3-1 this is
			// AMBIGUOUS (may have been acknowledged then had its marker damaged); a
			// complete frame can never be proven unaccepted by a missing marker.
			rep.BlockedDx = append(rep.BlockedDx, Diagnostic{
				Offset: int64(r.off), Seq: fr.seq, Key: fr.key,
				Reason: "complete frame without a valid accept marker: ambiguous; preserve + BLOCKED",
			})
			return rep, nil
		}
	}

	// Orphan accept check: every accept entry must map to a validated replay offset.
	// An accept referencing an offset with no/short/damaged frame is never discardable.
	for off, ar := range accByOff {
		if validated[off] {
			continue
		}
		rep.BlockedDx = append(rep.BlockedDx, Diagnostic{
			Offset: int64(off), Seq: ar.seq,
			Reason: "accept entry references a data offset with no validated frame (orphan accept): preserve + BLOCKED",
		})
	}

	// A corrupt/partial/garbage trailing region in the reservation or accept journals is
	// not a clean boundary: it must prevent append until an explicit recovery disposition
	// is applied, so no new acknowledgment is ever written behind unparsed bytes.
	if intentsTailDamaged {
		rep.BlockedDx = append(rep.BlockedDx, Diagnostic{
			Offset: int64(len(intentsB)),
			Reason: "intents journal has a corrupt, partial or out-of-order trailing reservation: preserve + BLOCKED until explicit recovery",
		})
	}
	if acceptsTailDamaged {
		rep.BlockedDx = append(rep.BlockedDx, Diagnostic{
			Offset: int64(len(accB)),
			Reason: "accepts journal has an unparsed/garbage trailing region: preserve + BLOCKED; no new acknowledgment until resolved",
		})
	}

	return rep, nil
}

// Apply performs the truncation decided by a Report, but ONLY when recovery is not
// blocked, and restores in-memory authority (sequence, accept chain, dedup) from the
// validated prefix. A blocked report never mutates the log.
func (w *WAL) Apply(rep Report) (string, error) {
	if rep.IsBlocked() {
		return "BLOCKED", fmt.Errorf("wal: recovery BLOCKED; %d ambiguous/damaged region(s) preserved for operator resolution", len(rep.BlockedDx))
	}
	if rep.TruncateAt >= 0 {
		if err := w.data.Truncate(rep.TruncateAt); err != nil {
			return "", err
		}
		if rep.truncIntentsAt >= 0 {
			if err := w.intents.Truncate(rep.truncIntentsAt); err != nil {
				return "", err
			}
		}
	}
	w.seq = rep.seq
	w.chainCRC = rep.chain
	w.dedup = map[string]uint64{}
	for k, s := range rep.dedup {
		w.dedup[k] = s
	}
	foldCommitted(w.dir, w.dedup, rep.seqKeys)
	w.appendable = true
	return "OK", nil
}

// parseFrameSpan parses a frame occupying EXACTLY the reserved span b and verifies it
// against the reservation's recorded CRC. The reserved length is authoritative, so a
// corrupted in-frame length cannot make a fully-written frame look like a short tail.
func parseFrameSpan(b []byte, wantCRC uint32) (frame, bool) {
	if len(b) < 1+8+4+4+4 {
		return frame{}, false
	}
	if b[0] != frameMagic {
		return frame{}, false
	}
	bodyEnd := len(b) - 4
	if crc32.Checksum(b[1:bodyEnd], crcTab) != wantCRC {
		return frame{}, false
	}
	if binary.BigEndian.Uint32(b[bodyEnd:]) != wantCRC {
		return frame{}, false
	}
	keyLen := int(binary.BigEndian.Uint32(b[9:13]))
	payLen := int(binary.BigEndian.Uint32(b[13:17]))
	if 1+8+4+4+keyLen+payLen+4 != len(b) {
		return frame{}, false
	}
	return frame{
		seq: binary.BigEndian.Uint64(b[1:9]),
		key: string(b[17 : 17+keyLen]),
		crc: wantCRC,
	}, true
}
