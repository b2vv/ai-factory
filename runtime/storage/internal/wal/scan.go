package wal

import (
	"encoding/binary"
	"errors"
	"fmt"
	"hash/crc32"
	"os"
	"path/filepath"
)

var ErrScanChanged = errors.New("wal: scan snapshot changed; restart bounded scan")

// Scanner is an ephemeral, bounded reader of the existing journal format. It
// grants no authority to delete: Compact still validates the COMPLETE journal
// before a flip. A changed snapshot restarts scanning, never reuses stale offsets.
// Callers serialize each Next with journal writes. No descriptors survive Next.
type Scanner struct {
	dir        string
	files      [3]os.FileInfo
	index, off int64
	seq        uint64
	chain      uint32
}

func NewScanner(dir string, maxBytes int64) (*Scanner, error) {
	n, e := ManagedBytes(dir)
	if e != nil {
		return nil, e
	}
	if maxBytes <= 0 || n > maxBytes {
		return nil, ErrMaintenanceBudget
	}
	s := &Scanner{dir: dir}
	for j, name := range []string{"data", "intents", "accepts"} {
		s.files[j], e = os.Stat(filepath.Join(dir, name))
		if e != nil {
			return nil, e
		}
		if !s.files[j].Mode().IsRegular() {
			return nil, fmt.Errorf("wal: nonregular scan source")
		}
	}
	if s.files[1].Size()%intentSize != 0 || s.files[2].Size()%acceptSize != 0 || s.files[1].Size()/intentSize != s.files[2].Size()/acceptSize {
		return nil, fmt.Errorf("wal: ambiguous intent/accept inventory; preserve + BLOCKED")
	}
	return s, nil
}
func (s *Scanner) Next(maxRecords int, maxBytes int64) ([]Record, bool, error) {
	if maxRecords <= 0 || maxBytes < intentSize+acceptSize {
		return nil, false, ErrMaintenanceBudget
	}
	var fs [3]*os.File
	for j, name := range []string{"data", "intents", "accepts"} {
		f, e := os.Open(filepath.Join(s.dir, name))
		if e != nil {
			return nil, false, e
		}
		fs[j] = f
		defer f.Close()
		st, e := f.Stat()
		if e != nil {
			return nil, false, e
		}
		old := s.files[j]
		// Appends may extend the immutable prefix; they must not starve a scan
		// behind retained quarantine. Replacement, shrinkage or same-size mutation
		// invalidates offsets. Complete-journal validation still precedes erasure.
		if !os.SameFile(old, st) || st.Size() < old.Size() || (old.Size() == st.Size() && !old.ModTime().Equal(st.ModTime())) {
			return nil, false, ErrScanChanged
		}
	}
	count := s.files[1].Size() / intentSize
	recs := []Record{}
	var spent int64
	for s.index < count && len(recs) < maxRecords {
		if spent > maxBytes-intentSize {
			break
		}
		var in [intentSize]byte
		var ac [acceptSize]byte
		if _, e := fs[1].ReadAt(in[:], s.index*intentSize); e != nil {
			return nil, false, e
		}
		spent += intentSize
		if in[0] != intentMagic || crc32.Checksum(in[:intentBody], crcTab) != binary.BigEndian.Uint32(in[intentBody:]) {
			return nil, false, fmt.Errorf("wal: corrupt reservation at %d; preserve + BLOCKED", s.index*intentSize)
		}
		seq := binary.BigEndian.Uint64(in[1:9])
		off := binary.BigEndian.Uint64(in[9:17])
		length := binary.BigEndian.Uint64(in[17:25])
		crc := binary.BigEndian.Uint32(in[25:29])
		if seq <= s.seq || off != uint64(s.off) || length < 21 || off > uint64(s.files[0].Size()) || length > uint64(s.files[0].Size())-off {
			return nil, false, fmt.Errorf("wal: ambiguous frame span at %d; preserve + BLOCKED", s.off)
		}
		if length > uint64(maxBytes)-uint64(intentSize+acceptSize) {
			return nil, false, ErrMaintenanceBudget
		}
		cost := int64(length) + acceptSize
		if spent > maxBytes-cost {
			break
		}
		frameBytes := make([]byte, int(length))
		if _, e := fs[0].ReadAt(frameBytes, s.off); e != nil {
			return nil, false, e
		}
		fr, ok := parseFrameSpan(frameBytes, crc)
		if !ok || fr.seq != seq {
			return nil, false, fmt.Errorf("wal: damaged frame at %d; preserve + BLOCKED", s.off)
		}
		if _, e := fs[2].ReadAt(ac[:], s.index*acceptSize); e != nil {
			return nil, false, e
		}
		kh := crc32.Checksum([]byte(fr.key), crcTab)
		chain := acceptChain(s.chain, seq, off, crc, kh)
		if ac[0] != acceptMagic || binary.BigEndian.Uint64(ac[1:9]) != seq || binary.BigEndian.Uint64(ac[9:17]) != off || binary.BigEndian.Uint32(ac[17:21]) != crc || binary.BigEndian.Uint32(ac[21:25]) != kh || binary.BigEndian.Uint32(ac[25:29]) != chain {
			return nil, false, fmt.Errorf("wal: damaged accept at %d; preserve + BLOCKED", s.index*acceptSize)
		}
		payload, _ := payloadOf(frameBytes)
		recs = append(recs, Record{Seq: seq, Key: fr.key, Payload: payload, Version: frameVersion(frameBytes[0])})
		spent += cost
		s.index++
		s.off += int64(length)
		s.seq = seq
		s.chain = chain
	}
	done := s.index == count
	if done && s.off != s.files[0].Size() {
		return nil, false, fmt.Errorf("wal: unclassified data tail at %d; maintenance preserves tail", s.off)
	}
	return recs, done, nil
}
