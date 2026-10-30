// Read accessor over the durable WAL so another subsystem (the durable control
// registry) can REUSE this journal's durability + fail-closed recovery instead of
// writing its own. It adds no journal/durability code: it runs the existing
// RecoverPlan and, only when recovery is clean, returns the accepted records with
// their payloads in sequence order. If recovery is BLOCKED (ambiguous/corrupt under
// the V3-1 rule) it returns the Report with no records so the caller fails closed.
package wal

import (
	"encoding/binary"
	"fmt"
	"os"
	"path/filepath"
	"sort"
)

// Record is one accepted WAL record with its payload.
type Record struct {
	Seq     uint64
	Key     string
	Payload []byte
}

// Accepted returns the validated accepted records (sequence-ordered) with payloads,
// together with the recovery Report. When rep.IsBlocked() is true the records slice is
// nil and the caller MUST treat the log as BLOCKED (fail closed) - never as empty.
func Accepted(dir string) ([]Record, Report, error) {
	rep, err := RecoverPlan(dir)
	if err != nil {
		return nil, Report{}, err
	}
	if rep.IsBlocked() {
		return nil, rep, nil
	}
	data, err := os.ReadFile(filepath.Join(dir, "data"))
	if err != nil {
		return nil, rep, err
	}
	recs := make([]Record, 0, len(rep.Replay))
	for _, d := range rep.Replay {
		payload, key, seq, ok := readFramePayload(data, d.Offset)
		if !ok {
			// A validated replay frame must be readable; if not, do not guess.
			return nil, rep, fmt.Errorf("wal: validated frame at offset %d is unreadable", d.Offset)
		}
		recs = append(recs, Record{Seq: seq, Key: key, Payload: payload})
	}
	sort.Slice(recs, func(i, j int) bool { return recs[i].Seq < recs[j].Seq })
	return recs, rep, nil
}

// MaxSeq returns the highest accepted sequence in recs (0 if none).
func MaxSeq(recs []Record) uint64 {
	var m uint64
	for _, r := range recs {
		if r.Seq > m {
			m = r.Seq
		}
	}
	return m
}

// readFramePayload extracts (payload, key, seq) from the frame beginning at off in the
// data file. It mirrors the frame layout written by frameBytes and does not trust the
// in-frame length beyond bounds-checking it against the available bytes.
func readFramePayload(data []byte, off int64) ([]byte, string, uint64, bool) {
	if off < 0 || off > int64(len(data)) {
		return nil, "", 0, false
	}
	b := data[off:]
	if len(b) < 1+8+4+4+4 || b[0] != frameMagic {
		return nil, "", 0, false
	}
	seq := binary.BigEndian.Uint64(b[1:9])
	keyLen := int(binary.BigEndian.Uint32(b[9:13]))
	payLen := int(binary.BigEndian.Uint32(b[13:17]))
	if keyLen < 0 || payLen < 0 {
		return nil, "", 0, false
	}
	total := 1 + 8 + 4 + 4 + keyLen + payLen + 4
	if total > len(b) {
		return nil, "", 0, false
	}
	key := string(b[17 : 17+keyLen])
	payload := append([]byte(nil), b[17+keyLen:17+keyLen+payLen]...)
	return payload, key, seq, true
}
