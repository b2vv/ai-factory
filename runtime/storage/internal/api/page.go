package api

import (
	"aifactory.local/storage/internal/archive"
	"crypto/aes"
	"crypto/cipher"
	"crypto/rand"
	"crypto/sha256"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"errors"
	"io"
)

const maxCursorPlaintext = 192 << 10
const maxCursorEncoded = 256 << 10

type pageCursor struct {
	Time                     *timeCursor `json:",omitempty"`
	Project, Query, Provider string
	IndexAfter               string `json:",omitempty"`
	After                    archive.Position
}

func (s *Server) cursorCipher() (cipher.AEAD, error) {
	k := sha256.Sum256([]byte("archive cursor v1\x00" + s.opSec))
	b, e := aes.NewCipher(k[:])
	if e != nil {
		return nil, e
	}
	return cipher.NewGCM(b)
}
func recentBinding(value string) string {
	digest := sha256.Sum256([]byte(value))
	return hex.EncodeToString(digest[:])
}
func (s *Server) encodeCursor(c pageCursor) (string, error) {
	if c.Time != nil {
		c.Project, c.Query, c.Provider = recentBinding(c.Project), recentBinding(c.Query), recentBinding(c.Provider)
		copy := *c.Time
		copy.Checkpoint.Project = ""
		c.Time = &copy
	}

	a, e := s.cursorCipher()
	if e != nil {
		return "", e
	}
	n := make([]byte, a.NonceSize())
	if _, e = io.ReadFull(rand.Reader, n); e != nil {
		return "", e
	}
	b, e := json.Marshal(c)
	if e != nil {
		return "", e
	}
	if len(b) > maxCursorPlaintext || base64.RawURLEncoding.EncodedLen(len(b)+a.NonceSize()+a.Overhead()) > maxCursorEncoded {
		return "", errors.New("cursor too large")
	}
	return base64.RawURLEncoding.EncodeToString(a.Seal(n, n, b, nil)), nil
}
func (s *Server) decodeCursor(v string) (pageCursor, error) {
	var c pageCursor
	if len(v) > maxCursorEncoded {
		return c, errors.New("cursor too large")
	}
	a, e := s.cursorCipher()
	if e != nil {
		return c, e
	}
	b, e := base64.RawURLEncoding.DecodeString(v)
	if e != nil || len(b) < a.NonceSize() || len(b) > maxCursorPlaintext+a.NonceSize()+a.Overhead() {
		return c, errors.New("invalid cursor")
	}
	plain, e := a.Open(nil, b[:a.NonceSize()], b[a.NonceSize():], nil)
	if e != nil {
		return c, errors.New("invalid cursor")
	}
	if len(plain) > maxCursorPlaintext {
		return c, errors.New("cursor too large")
	}
	e = json.Unmarshal(plain, &c)
	return c, e
}
