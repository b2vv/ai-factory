package wal

import (
	"errors"
	"hash/crc32"
)

var ErrVersionConflict = errors.New("wal: retry format differs or is not provable")

const frameMagicV2 = 'G'

// AcceptV2 is an inactive format foundation. Production intake/control writers
// must continue using Accept until metadata projection and migration gates pass.
func (w *WAL) AcceptV2(key string, payload []byte) (Receipt, error) {
	return w.acceptVersion(key, payload, 2)
}

func frameVersion(magic byte) uint8 {
	if magic == frameMagic {
		return 1
	}
	if magic == frameMagicV2 {
		return 2
	}
	return 0
}

// Legacy CRC bytes are unchanged. V2 binds its format marker too, so changing G
// to F cannot make an older reader reinterpret a valid new frame as legacy.
func frameChecksum(frame []byte) uint32 {
	body := frame[:len(frame)-4]
	if frame[0] == frameMagic {
		body = body[1:]
	}
	return crc32.Checksum(body, crcTab)
}
