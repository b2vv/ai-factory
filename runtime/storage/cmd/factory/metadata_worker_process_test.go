//go:build integration

package main

import (
	"aifactory.local/storage/internal/archive"
	"aifactory.local/storage/internal/budget"
	"aifactory.local/storage/internal/config"
	"aifactory.local/storage/internal/control"
	"aifactory.local/storage/internal/ingest"
	"aifactory.local/storage/internal/wal"
	"bytes"
	"encoding/binary"
	"encoding/json"
	"go.mongodb.org/mongo-driver/bson"
	"io"
	"net"
	"net/http"
	"net/url"
	"path/filepath"
	"sync"
	"sync/atomic"
	"testing"
	"time"
)

// This fixture only intercepts inserts through its private loopback listener.
// Other test clients and the shared Mongo server are never stopped or reconfigured.
func metadataInsertFaultProxy(t *testing.T, uri string) (string, *atomic.Bool, *atomic.Int64) {
	t.Helper()
	u, err := url.Parse(uri)
	if err != nil {
		t.Fatal(err)
	}
	upstream := u.Host
	ln, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatal(err)
	}
	u.Host = ln.Addr().String()
	blocked := new(atomic.Bool)
	rejected := new(atomic.Int64)
	var mu sync.Mutex
	conns := map[net.Conn]bool{}
	var wg sync.WaitGroup
	acceptDone := make(chan struct{})
	go func() {
		defer close(acceptDone)
		for {
			client, err := ln.Accept()
			if err != nil {
				return
			}
			mu.Lock()
			conns[client] = true
			mu.Unlock()
			wg.Add(1)
			go func() {
				defer wg.Done()
				defer client.Close()
				defer func() { mu.Lock(); delete(conns, client); mu.Unlock() }()
				backend, err := net.DialTimeout("tcp", upstream, 3*time.Second)
				if err != nil {
					return
				}
				defer backend.Close()
				var writes sync.Mutex
				repliesDone := make(chan struct{})
				go func() {
					defer close(repliesDone)
					buffer := make([]byte, 32768)
					for {
						n, e := backend.Read(buffer)
						if n > 0 {
							writes.Lock()
							_, w := client.Write(buffer[:n])
							writes.Unlock()
							if w != nil {
								return
							}
						}
						if e != nil {
							return
						}
					}
				}()
				defer func() { backend.Close(); client.Close(); <-repliesDone }()
				for {
					header := make([]byte, 16)
					if _, err := io.ReadFull(client, header); err != nil {
						return
					}
					size := int(binary.LittleEndian.Uint32(header))
					if size < 16 || size > 32<<20 {
						return
					}
					packet := make([]byte, size)
					copy(packet, header)
					if _, err := io.ReadFull(client, packet[16:]); err != nil {
						return
					}
					insert := false
					if binary.LittleEndian.Uint32(packet[12:16]) == 2013 && size >= 26 && packet[20] == 0 {
						length := int(binary.LittleEndian.Uint32(packet[21:25]))
						if length >= 5 && 21+length <= size {
							name, ok := bson.Raw(packet[21 : 21+length]).Lookup("insert").StringValueOK()
							insert = ok && name == "archive"
						}
					}
					if blocked.Load() && insert {
						rejected.Add(1)
						doc, _ := bson.Marshal(bson.D{{Key: "ok", Value: float64(0)}, {Key: "code", Value: int32(12345)}, {Key: "errmsg", Value: "synthetic isolated insert outage"}})
						reply := make([]byte, 21+len(doc))
						binary.LittleEndian.PutUint32(reply, uint32(len(reply)))
						copy(reply[8:12], packet[4:8])
						binary.LittleEndian.PutUint32(reply[12:16], 2013)
						copy(reply[21:], doc)
						writes.Lock()
						_, err = client.Write(reply)
						writes.Unlock()
						if err != nil {
							return
						}
						continue
					}
					if _, err := backend.Write(packet); err != nil {
						return
					}
				}
			}()
		}
	}()
	t.Cleanup(func() {
		ln.Close()
		<-acceptDone
		mu.Lock()
		for c := range conns {
			c.Close()
		}
		mu.Unlock()
		wg.Wait()
	})
	return u.String(), blocked, rejected
}

func TestProcessMetadataWorkerRecoversPostListenInsertOutage(t *testing.T) {
	f := metadataFixture(t)
	proxy, blocked, rejected := metadataInsertFaultProxy(t, f.cfg.MongoURI)
	f.cfg.MongoURI = proxy
	f.writeConfig(t)
	f.closeWriter(t)
	addr, stop := f.start(t, buildFactory(t, t.TempDir()))
	blocked.Store(true)
	record := archive.Record{Project: "p", Provider: "synthetic", SourceInstance: "source", SessionID: "s", MessageID: "worker", Type: archive.TypeMessage, Text: "worker needle", ConsentEpoch: 1}
	raw, _ := json.Marshal(map[string]any{"project": "p", "provider": "synthetic", "source_instance": "source", "messages": []map[string]any{{"session_id": "s", "message_id": "worker", "text": "worker needle"}}})
	req, _ := http.NewRequest("POST", "http://"+addr+"/v1/capture", bytes.NewReader(raw))
	req.Header.Set("X-Operator-Secret", "smoke-secret")
	resp, err := (&http.Client{Timeout: 10 * time.Second}).Do(req)
	if err != nil {
		t.Fatal(err)
	}
	var body map[string]any
	err = json.NewDecoder(resp.Body).Decode(&body)
	resp.Body.Close()
	if err != nil || resp.StatusCode != 503 || rejected.Load() == 0 {
		t.Fatal("fixture did not fail after WAL acceptance", resp.StatusCode, body, err)
	}
	receipts, ok := body["receipts"].([]any)
	if !ok || len(receipts) != 1 || receipts[0] != archive.IdentityKey(record) || body["accepted"] != float64(0) {
		t.Fatal("durable pending receipt missing", body)
	}
	if _, found, err := f.source.LookupEnvelope(record); err != nil || found {
		t.Fatal("failed insert reached source", found, err)
	}
	blocked.Store(false)
	// No producer retry and no server restart: only the actual background worker can finish.
	deadline := time.Now().Add(12 * time.Second)
	for {
		got, found, err := f.source.LookupEnvelope(record)
		if err != nil {
			t.Fatal(err)
		}
		if found {
			if got.Record != record || got.Metadata.Ordinal != 1 || got.Metadata.CapturedAt == nil {
				t.Fatal("worker changed accepted source", got)
			}
			break
		}
		if time.Now().After(deadline) {
			t.Fatal("post-LISTEN recovery required producer retry")
		}
		time.Sleep(50 * time.Millisecond)
	}
	stop()
	ctl, err := control.Open(f.state)
	if err != nil {
		t.Fatal(err)
	}
	state, active, err := ctl.ArchiveState("p")
	ctl.Close()
	if err != nil || !active || state.CommittedOrdinal != 1 || state.Pending != nil {
		t.Fatal("worker left transaction incomplete", state, err)
	}
	ledger, err := budget.Open(filepath.Join(f.state, "budget.bin"), nil)
	if err != nil {
		t.Fatal(err)
	}
	pending := ledger.Snapshot().Pending
	ledger.Close()
	if len(pending) != 0 {
		t.Fatal("worker left budget liability", pending)
	}
	checkpoint, found, err := f.index.Checkpoint("p")
	if err != nil || !found || !checkpoint.Complete || checkpoint.Ordinal != state.CommittedOrdinal || checkpoint.SourceGeneration != state.Generation {
		t.Fatal("worker left index incomplete", checkpoint, err)
	}
	dir := filepath.Join(f.state, "ingest", "wal")
	intake, err := ingest.OpenExisting(dir, config.NewAccountant(f.cfg), f.source)
	if err != nil {
		t.Fatal(err)
	}
	progress, err := intake.Progress()
	intake.Close()
	if err != nil || progress.Blocked || progress.Accepted != 1 || progress.Processed != 1 || progress.Depth != 0 {
		t.Fatal("worker left unprocessed intake", progress, err)
	}
	frames, report, err := wal.Accepted(dir)
	if err != nil || report.IsBlocked() || len(frames) != 1 {
		t.Fatal("accepted envelope unavailable", err)
	}
	accepted, err := archive.DecodeEnvelope(frames[0].Version, frames[0].Payload)
	if err != nil {
		t.Fatal(err)
	}
	got, found, err := f.source.LookupEnvelope(record)
	if err != nil || !found {
		t.Fatal(err)
	}
	a, err := archive.EncodeEnvelope(accepted)
	if err != nil {
		t.Fatal(err)
	}
	b, err := archive.EncodeEnvelope(got)
	if err != nil || !bytes.Equal(a, b) {
		t.Fatal("worker changed accepted metadata", err)
	}
}
