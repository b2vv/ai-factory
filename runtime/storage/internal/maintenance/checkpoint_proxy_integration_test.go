//go:build integration

package maintenance

import (
	"encoding/binary"
	"io"
	"net"
	"net/url"
	"strings"
	"sync"
	"sync/atomic"
	"testing"
)

// A private simple-protocol proxy injects one server error on the final proof
// read of an already-complete operator retry. Production code/binary is unchanged.
func checkpointFailureProxy(t *testing.T, dsn string) (string, *atomic.Bool) {
	t.Helper()
	u, err := url.Parse(dsn)
	if err != nil {
		t.Fatal(err)
	}
	upstream := u.Host
	listener, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatal(err)
	}
	var calls atomic.Int32
	fired := new(atomic.Bool)
	var mu sync.Mutex
	connections := []net.Conn{}
	stopped := false
	t.Cleanup(func() {
		listener.Close()
		mu.Lock()
		stopped = true
		for _, c := range connections {
			c.Close()
		}
		mu.Unlock()
	})
	go func() {
		for {
			front, err := listener.Accept()
			if err != nil {
				return
			}
			mu.Lock()
			if stopped {
				front.Close()
				mu.Unlock()
				return
			}
			connections = append(connections, front)
			mu.Unlock()
			go func() {
				defer front.Close()
				back, err := net.Dial("tcp", upstream)
				if err != nil {
					return
				}
				defer back.Close()
				mu.Lock()
				if stopped {
					back.Close()
					mu.Unlock()
					return
				}
				connections = append(connections, back)
				mu.Unlock()
				// Startup packet has no message type. TLS is explicitly disabled in this fixture.
				header := make([]byte, 4)
				if _, err := io.ReadFull(front, header); err != nil {
					return
				}
				size := int(binary.BigEndian.Uint32(header))
				if size < 4 || size > 1<<20 {
					return
				}
				payload := make([]byte, size-4)
				if _, err := io.ReadFull(front, payload); err != nil {
					return
				}
				if _, err := back.Write(append(header, payload...)); err != nil {
					return
				}
				var writeMu sync.Mutex
				go func() {
					frame := make([]byte, 5)
					for {
						if _, err := io.ReadFull(back, frame); err != nil {
							front.Close()
							return
						}
						n := int(binary.BigEndian.Uint32(frame[1:]))
						if n < 4 || n > 16<<20 {
							front.Close()
							return
						}
						body := make([]byte, n-4)
						if _, err := io.ReadFull(back, body); err != nil {
							front.Close()
							return
						}
						writeMu.Lock()
						_, err := front.Write(append(append([]byte{}, frame...), body...))
						writeMu.Unlock()
						if err != nil {
							return
						}
					}
				}()
				for {
					frame := make([]byte, 5)
					if _, err := io.ReadFull(front, frame); err != nil {
						return
					}
					n := int(binary.BigEndian.Uint32(frame[1:]))
					if n < 4 || n > 16<<20 {
						return
					}
					body := make([]byte, n-4)
					if _, err := io.ReadFull(front, body); err != nil {
						return
					}
					if frame[0] == 'Q' && strings.HasPrefix(string(body), "SELECT project,source_generation,projection_generation,policy_revision,ordinal,complete FROM archive_checkpoint") && calls.Add(1) == 3 {
						fired.Store(true)
						fields := []byte("SERROR\x00VERROR\x00CXX000\x00Mfixture-checkpoint-read-failure\x00\x00")
						response := make([]byte, 5)
						response[0] = 'E'
						binary.BigEndian.PutUint32(response[1:], uint32(len(fields)+4))
						response = append(response, fields...)
						response = append(response, 'Z', 0, 0, 0, 5, 'I')
						writeMu.Lock()
						_, err := front.Write(response)
						writeMu.Unlock()
						if err != nil {
							return
						}
						continue
					}
					if _, err := back.Write(append(frame, body...)); err != nil {
						return
					}
				}
			}()
		}
	}()
	u.Host = listener.Addr().String()
	q := u.Query()
	q.Set("sslmode", "disable")
	q.Set("default_query_exec_mode", "simple_protocol")
	u.RawQuery = q.Encode()
	return u.String(), fired
}
