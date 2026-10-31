// Compaction PHYSICALLY removes selected records from the journal (PLAN §11.1 "queue
// compaction/erasure") while preserving every retained record and the V3-1 fail-closed
// contract. It is the WAL half of physical deletion: the serve-gate only HIDES, and the
// archive Purge only erases the archive copy; Compact erases the intake-journal bytes so a
// later WAL re-drain cannot re-materialize the dropped payload.
//
// Crash-safety (generation flip via a durable commit sentinel):
//
//  1. Refuse outright if recovery is BLOCKED/ambiguous. Compaction never resolves a
//     preserve+BLOCK tail by deleting bytes it cannot prove were unaccepted.
//  2. Stage a complete new generation (data/intents/accepts/committed.idx) under
//     compact.tmp/, each file fsync'd, then the staging dir fsync'd. The live journal is
//     untouched up to this point, so a crash here loses only the staged copy.
//  3. Write the durable commit sentinel compact.commit (fsync + dir fsync). This is the
//     atomic commit point: once the sentinel is durable the new generation WINS.
//  4. Install: rename each staged file over its live name, fsync the dir, remove the
//     sentinel (fsync dir), remove the staging dir (fsync dir).
//
// resumeCompaction (run at the very top of Open, before any journal file is opened) makes
// the flip crash-idempotent:
//   - sentinel present  -> finish the install (re-run the renames that have not happened
//     yet; a staged file already renamed away is simply skipped), then clear it. The live
//     set is never consumed in a half-installed state because the sentinel forces the
//     remaining renames first.
//   - sentinel absent but a staging dir exists -> an aborted pre-commit staging; discard it.
//     (Post-install the staging dir is empty, so discarding is always safe here.)
//
// A dropped record's key is intentionally absent from the rebuilt dedup index, so the same
// identity would be treated as NEW on a future append. Resurrection is prevented one layer
// up by the RETAINED deletion barrier (checked on every publish/serve/restore), exactly as
// for the archive Purge; Compact deliberately does not itself remember what it erased.
package wal

import (
	"encoding/binary"
	"fmt"
	"hash/crc32"
	"os"
	"path/filepath"
)

const (
	compactStaging  = "compact.tmp"
	compactSentinel = "compact.commit"
)

// sentinelBytes is the exact content of a durable commit sentinel. A partially written
// sentinel will not match and is treated as "not committed" (the staging is discarded),
// so a torn sentinel can never install a half-staged generation.
var sentinelBytes = func() []byte {
	magic := []byte("WAL-COMPACT-COMMIT-v1")
	return binary.BigEndian.AppendUint32(append([]byte(nil), magic...), crc32.Checksum(magic, crcTab))
}()

// journalFiles are the four files that constitute one journal generation.
var journalFiles = []string{"data", "intents", "accepts", "committed.idx"}

// CompactResult reports what compaction did.
type CompactResult struct {
	Kept    int
	Dropped int
}

// Compact rewrites the journal in dir, keeping only records for which keep(key, payload)
// returns true and physically dropping the rest. It must be called with the journal files
// CLOSED (the caller closes its *WAL first and reopens afterwards); it operates on the
// directory, not on open descriptors. It refuses a BLOCKED/ambiguous journal and never
// removes the journal as a whole (it always leaves a valid, possibly empty, generation).
func Compact(dir string, keep func(key string, payload []byte) bool) (CompactResult, error) {
	// Resolve any in-flight flip from a previous crash before reading the journal.
	if err := resumeCompaction(dir); err != nil {
		return CompactResult{}, err
	}
	recs, rep, err := Accepted(dir)
	if err != nil {
		return CompactResult{}, err
	}
	if rep.IsBlocked() {
		return CompactResult{}, fmt.Errorf("wal: refusing to compact a BLOCKED journal (%d ambiguous/damaged region(s)); resolve recovery first", len(rep.BlockedDx))
	}

	staging := filepath.Join(dir, compactStaging)
	if err := os.RemoveAll(staging); err != nil {
		return CompactResult{}, err
	}
	if err := os.MkdirAll(staging, 0o700); err != nil {
		return CompactResult{}, err
	}

	res, err := writeGeneration(staging, recs, keep)
	if err != nil {
		_ = os.RemoveAll(staging)
		return CompactResult{}, err
	}
	if err := syncDir(staging); err != nil {
		_ = os.RemoveAll(staging)
		return CompactResult{}, fmt.Errorf("wal: fsync of compaction staging failed: %w", err)
	}

	// Commit point: the sentinel's durability decides which generation wins.
	if err := writeSentinel(dir); err != nil {
		_ = os.RemoveAll(staging)
		return CompactResult{}, err
	}
	if err := installGeneration(dir); err != nil {
		return CompactResult{}, err
	}
	return res, nil
}

// writeGeneration writes a fresh, repacked journal into dir from the kept subset of recs.
// Original sequence numbers are PRESERVED (gaps are allowed and strictly-increasing order is
// kept), so the ingest progress watermark keeps its meaning; only data offsets are rebuilt.
func writeGeneration(dir string, recs []Record, keep func(key string, payload []byte) bool) (CompactResult, error) {
	data, err := os.OpenFile(filepath.Join(dir, "data"), os.O_CREATE|os.O_WRONLY|os.O_TRUNC, 0o600)
	if err != nil {
		return CompactResult{}, err
	}
	defer data.Close()
	intents, err := os.OpenFile(filepath.Join(dir, "intents"), os.O_CREATE|os.O_WRONLY|os.O_TRUNC, 0o600)
	if err != nil {
		return CompactResult{}, err
	}
	defer intents.Close()
	accepts, err := os.OpenFile(filepath.Join(dir, "accepts"), os.O_CREATE|os.O_WRONLY|os.O_TRUNC, 0o600)
	if err != nil {
		return CompactResult{}, err
	}
	defer accepts.Close()
	cidx, err := os.OpenFile(filepath.Join(dir, "committed.idx"), os.O_CREATE|os.O_WRONLY|os.O_TRUNC, 0o600)
	if err != nil {
		return CompactResult{}, err
	}
	defer cidx.Close()

	var res CompactResult
	var off uint64
	var chain uint32
	for _, rec := range recs {
		if keep != nil && !keep(rec.Key, rec.Payload) {
			res.Dropped++
			continue
		}
		res.Kept++
		fb := frameBytes(rec.Seq, []byte(rec.Key), rec.Payload)
		frameCRC := crc32.Checksum(fb[1:len(fb)-4], crcTab)
		keyHash := crc32.Checksum([]byte(rec.Key), crcTab)

		if _, err := intents.Write(intentBytes(rec.Seq, off, uint64(len(fb)), frameCRC)); err != nil {
			return CompactResult{}, err
		}
		if _, err := data.Write(fb); err != nil {
			return CompactResult{}, err
		}
		chain = acceptChain(chain, rec.Seq, off, frameCRC, keyHash)
		if _, err := accepts.Write(acceptBytes(rec.Seq, off, frameCRC, keyHash, chain)); err != nil {
			return CompactResult{}, err
		}
		if _, err := cidx.Write(committedRec(rec.Key, rec.Seq)); err != nil {
			return CompactResult{}, err
		}
		off += uint64(len(fb))
	}
	for _, f := range []*os.File{data, intents, accepts, cidx} {
		if err := f.Sync(); err != nil {
			return CompactResult{}, fmt.Errorf("wal: fsync of staged generation failed: %w", err)
		}
	}
	return res, nil
}

// acceptBytes builds a fixed 29-byte accept entry with a precomputed chain value (the free
// function form of (*WAL).acceptEntry, usable without a live WAL).
func acceptBytes(seq, frameOff uint64, frameCRC, keyHash, chain uint32) []byte {
	b := make([]byte, 0, acceptSize)
	b = append(b, acceptMagic)
	b = binary.BigEndian.AppendUint64(b, seq)
	b = binary.BigEndian.AppendUint64(b, frameOff)
	b = binary.BigEndian.AppendUint32(b, frameCRC)
	b = binary.BigEndian.AppendUint32(b, keyHash)
	b = binary.BigEndian.AppendUint32(b, chain)
	return b
}

// committedRec builds a dedup-index record identical to (*WAL).appendCommitted's layout.
func committedRec(key string, seq uint64) []byte {
	rec := make([]byte, 0, 4+8+len(key)+4)
	rec = binary.BigEndian.AppendUint32(rec, uint32(len(key)))
	rec = binary.BigEndian.AppendUint64(rec, seq)
	rec = append(rec, key...)
	return binary.BigEndian.AppendUint32(rec, crc32.Checksum(rec, crcTab))
}

// writeSentinel writes the durable commit sentinel (temp + fsync + rename + dir fsync).
var writeSentinel = func(dir string) error {
	tmp := filepath.Join(dir, compactSentinel+".tmp")
	f, err := os.OpenFile(tmp, os.O_CREATE|os.O_TRUNC|os.O_WRONLY, 0o600)
	if err != nil {
		return err
	}
	if _, err := f.Write(sentinelBytes); err != nil {
		f.Close()
		return err
	}
	if err := f.Sync(); err != nil {
		f.Close()
		return err
	}
	if err := f.Close(); err != nil {
		return err
	}
	if err := os.Rename(tmp, filepath.Join(dir, compactSentinel)); err != nil {
		return err
	}
	return syncDir(dir)
}

// installGeneration is the post-sentinel step (also re-run by resumeCompaction): move each
// staged file over its live name, fsync the dir, then clear the sentinel and staging dir. It
// is a package var so a test can inject a crash between individual renames.
var installGeneration = func(dir string) error {
	staging := filepath.Join(dir, compactStaging)
	for _, name := range journalFiles {
		src := filepath.Join(staging, name)
		if _, err := os.Stat(src); err != nil {
			if os.IsNotExist(err) {
				continue // already installed on an earlier (crashed) attempt
			}
			return err
		}
		if err := os.Rename(src, filepath.Join(dir, name)); err != nil {
			return err
		}
	}
	if err := syncDir(dir); err != nil {
		return err
	}
	if err := os.Remove(filepath.Join(dir, compactSentinel)); err != nil && !os.IsNotExist(err) {
		return err
	}
	if err := syncDir(dir); err != nil {
		return err
	}
	if err := os.RemoveAll(staging); err != nil {
		return err
	}
	return syncDir(dir)
}

// resumeCompaction converges any interrupted flip to a single generation. It is called at
// the very top of Open, before journal descriptors are opened, so RecoverPlan never sees a
// half-installed mixture of old and new files.
func resumeCompaction(dir string) error {
	sentinel := filepath.Join(dir, compactSentinel)
	b, err := os.ReadFile(sentinel)
	switch {
	case err == nil:
		if !bytesEqual(b, sentinelBytes) {
			// Torn/partial sentinel: the commit point was not durably reached. Discard the
			// staged generation; the untouched live journal remains authoritative.
			if rmErr := os.RemoveAll(filepath.Join(dir, compactStaging)); rmErr != nil {
				return rmErr
			}
			if rmErr := os.Remove(sentinel); rmErr != nil && !os.IsNotExist(rmErr) {
				return rmErr
			}
			return syncDir(dir)
		}
		return installGeneration(dir) // committed: finish (idempotently)
	case os.IsNotExist(err):
		// No commit sentinel. Any leftover staging is a pre-commit abort (post-install the
		// staging dir is empty), so discarding it is safe.
		staging := filepath.Join(dir, compactStaging)
		if _, statErr := os.Stat(staging); statErr == nil {
			if rmErr := os.RemoveAll(staging); rmErr != nil {
				return rmErr
			}
			return syncDir(dir)
		}
		return nil
	default:
		return err
	}
}

func bytesEqual(a, b []byte) bool {
	if len(a) != len(b) {
		return false
	}
	for i := range a {
		if a[i] != b[i] {
			return false
		}
	}
	return true
}
