//go:build integration

package main

import (
	"aifactory.local/storage/internal/archive"
	"aifactory.local/storage/internal/budget"
	"aifactory.local/storage/internal/budgetenv"
	"aifactory.local/storage/internal/config"
	"aifactory.local/storage/internal/control"
	"aifactory.local/storage/internal/ingest"
	"aifactory.local/storage/internal/maintenance"
	"aifactory.local/storage/internal/registry"
	"aifactory.local/storage/internal/search"
	"aifactory.local/storage/internal/workflow"
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"github.com/jackc/pgx/v5"
	"go.mongodb.org/mongo-driver/mongo"
	"go.mongodb.org/mongo-driver/mongo/options"
	"net/http"
	"net/url"
	"os"
	"os/exec"
	"path/filepath"
	"reflect"
	"strings"
	"syscall"
	"testing"
	"time"
)

type metadataProcessFixture struct {
	state, configPath, token string
	cfg                      config.Config
	ctl                      *control.Durable
	intake                   *ingest.Ingestor
	source                   *archive.MongoStore
	index                    *search.Store
}

func metadataFixture(t *testing.T) *metadataProcessFixture {
	t.Helper()
	ctx := context.Background()
	uri, dsn := os.Getenv("MONGO_URI"), os.Getenv("PG_DSN")
	if uri == "" || dsn == "" {
		t.Skip("real metadata startup requires isolated MONGO_URI and PG_DSN")
	}
	root := t.TempDir()
	db := fmt.Sprintf("metadata_startup_%d", time.Now().UnixNano())
	schema := db
	admin, e := pgx.Connect(ctx, dsn)
	if e != nil {
		t.Fatal(e)
	}
	if _, e = admin.Exec(ctx, "CREATE SCHEMA "+pgx.Identifier{schema}.Sanitize()); e != nil {
		t.Fatal(e)
	}
	t.Cleanup(func() { admin.Exec(ctx, "DROP SCHEMA "+pgx.Identifier{schema}.Sanitize()+" CASCADE"); admin.Close(ctx) })
	u, e := url.Parse(dsn)
	if e != nil {
		t.Fatal(e)
	}
	q := u.Query()
	q.Set("search_path", schema)
	u.RawQuery = q.Encode()
	mc, e := mongo.Connect(ctx, options.Client().ApplyURI(uri))
	if e != nil {
		t.Fatal(e)
	}
	t.Cleanup(func() { mc.Database(db).Drop(ctx); mc.Disconnect(ctx) })
	f := &metadataProcessFixture{state: filepath.Join(root, "state"), configPath: filepath.Join(root, "config.json"), token: filepath.Join(root, "operator.json"), cfg: config.Default()}
	f.cfg.MongoEnabled = true
	f.cfg.MongoURI = uri
	f.cfg.MongoDB = db
	f.cfg.MongoCollection = "archive"
	f.cfg.PostgresEnabled = true
	f.cfg.PostgresDSN = u.String()
	f.cfg.CaptureEnabled = true
	f.source, e = archive.OpenMongo(ctx, uri, db, "archive")
	if e != nil {
		t.Fatal(e)
	}
	t.Cleanup(func() { f.source.Close() })
	pg, e := workflow.OpenPostgres(ctx, u.String())
	if e != nil {
		t.Fatal(e)
	}
	defer pg.Close()
	f.ctl, e = control.InitializeBudgeted(f.state, f.cfg)
	if e != nil {
		t.Fatal(e)
	}
	op := registry.Principal{Kind: registry.Operator}
	if e = f.ctl.MintProject(op, "p", "fixture"); e != nil {
		t.Fatal(e)
	}
	if _, e = f.ctl.SetConsent(op, "p", "synthetic", "capture", true); e != nil {
		t.Fatal(e)
	}
	if e = f.ctl.IssueGrant(op, registry.Grant{PrincipalID: "reader", Kind: registry.Agent, Projects: map[string]bool{"p": true}, Ops: map[registry.Op]bool{registry.OpSearch: true, registry.OpArchiveQuery: true}, Secret: "synthetic-reader"}); e != nil {
		t.Fatal(e)
	}
	f.intake, e = ingest.Open(filepath.Join(f.state, "ingest", "wal"), config.NewAccountant(f.cfg), f.source)
	if e != nil {
		t.Fatal(e)
	}
	env, e := budgetenv.Open(f.state, &f.cfg)
	if e != nil {
		t.Fatal(e)
	}
	t.Cleanup(func() { env.Close() })
	if e = f.ctl.AttachBudget(env.DetachLedger()); e != nil {
		t.Fatal(e)
	}
	if e = f.intake.SetBudget(f.ctl.Budget()); e != nil {
		t.Fatal(e)
	}
	if e = f.ctl.BeginArchiveMigration(op, "p", "generation"); e != nil {
		t.Fatal(e)
	}
	if e = maintenance.PrepareArchiveSchema(ctx, f.ctl, op, "p", f.source, pg); e != nil {
		t.Fatal(e)
	}
	f.index, e = search.Open(ctx, u.String())
	if e != nil {
		t.Fatal(e)
	}
	t.Cleanup(func() { f.index.Close() })
	if e = f.ctl.WithArchiveTransaction(op, "p", func(tx *control.ArchiveTransaction) error {
		if _, e := f.index.ProjectArchive(tx, f.source, func(archive.Record) bool { return true }); e != nil {
			return e
		}
		return tx.FinishMigration(func(s control.ArchiveState) error {
			c, found, e := f.index.Checkpoint("p")
			if e != nil {
				return e
			}
			if !found || !c.Complete || c.Ordinal != s.CommittedOrdinal {
				return search.ErrCheckpoint
			}
			return nil
		})
	}); e != nil {
		t.Fatal(e)
	}
	if e = search.MarkRequired(f.state); e != nil {
		t.Fatal(e)
	}
	writeFile0600(t, f.token, `{"id":"operator","secret":"smoke-secret"}`)
	f.writeConfig(t)
	return f
}
func (f *metadataProcessFixture) writeConfig(t *testing.T) {
	t.Helper()
	raw, e := json.Marshal(map[string]any{"mongo_enabled": true, "mongo_uri": f.cfg.MongoURI, "mongo_db": f.cfg.MongoDB, "mongo_collection": f.cfg.MongoCollection, "postgres_enabled": f.cfg.PostgresEnabled, "postgres_dsn": f.cfg.PostgresDSN, "capture_enabled": true})
	if e != nil {
		t.Fatal(e)
	}
	writeFile0600(t, f.configPath, string(raw))
}
func (f *metadataProcessFixture) closeWriter(t *testing.T) {
	t.Helper()
	if e := f.intake.Close(); e != nil {
		t.Fatal(e)
	}
	if e := f.ctl.Close(); e != nil {
		t.Fatal(e)
	}
}
func (f *metadataProcessFixture) start(t *testing.T, bin string) (string, func()) {
	t.Helper()
	cmd := exec.Command(bin, "-state", f.state, "-config", f.configPath, "-operator-token", f.token, "-listen", "127.0.0.1:0")
	out, e := cmd.StdoutPipe()
	if e != nil {
		t.Fatal(e)
	}
	var diagnostics bytes.Buffer
	cmd.Stderr = &diagnostics
	if e = cmd.Start(); e != nil {
		t.Fatal(e)
	}
	t.Cleanup(func() {
		if cmd.Process != nil {
			cmd.Process.Kill()
		}
	})
	addr := awaitListen(t, out, cmd)
	stopped := false
	stop := func() {
		if stopped {
			return
		}
		stopped = true
		cmd.Process.Signal(syscall.SIGTERM)
		done := make(chan error, 1)
		go func() { done <- cmd.Wait() }()
		select {
		case e := <-done:
			if e != nil {
				t.Errorf("process exit: %v %s", e, diagnostics.String())
			}
		case <-time.After(5 * time.Second):
			cmd.Process.Kill()
			<-done
			t.Error("graceful stop timeout")
		}
	}
	t.Cleanup(stop)
	return addr, stop
}
func (f *metadataProcessFixture) refuse(t *testing.T, bin string) {
	t.Helper()
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	out, e := exec.CommandContext(ctx, bin, "-state", f.state, "-config", f.configPath, "-operator-token", f.token, "-listen", "127.0.0.1:0").CombinedOutput()
	if e == nil || ctx.Err() != nil || strings.Contains(string(out), "LISTEN ") {
		t.Fatalf("unsafe metadata startup: %s %v", out, e)
	}
}
func metadataGet(t *testing.T, addr, path string) (int, map[string]any) {
	t.Helper()
	req, _ := http.NewRequest("GET", "http://"+addr+path, nil)
	req.Header.Set("X-Principal-Id", "reader")
	req.Header.Set("X-Grant-Epoch", "1")
	req.Header.Set("X-Secret", "synthetic-reader")
	client := http.Client{Timeout: 3 * time.Second}
	resp, e := client.Do(req)
	if e != nil {
		t.Fatal(e)
	}
	defer resp.Body.Close()
	var body map[string]any
	if e = json.NewDecoder(resp.Body).Decode(&body); e != nil {
		t.Fatal(e)
	}
	return resp.StatusCode, body
}
func TestProcessMetadataStartupRecovery(t *testing.T) {
	if os.Getenv("MONGO_URI") == "" || os.Getenv("PG_DSN") == "" {
		t.Skip("isolated real databases required")
	}
	bin := buildFactory(t, t.TempDir())
	op := registry.Principal{Kind: registry.Operator}
	for _, phase := range []string{"clean", "reserved", "accepted", "projected", "committed", "projection-before", "projection-after", "projection-disabled", "proof-mismatch", "corrupt-data", "missing-data", "missing-intents", "missing-accepts", "missing-committed.idx", "missing-directory"} {
		t.Run(phase, func(t *testing.T) {
			f := metadataFixture(t)
			record := archive.Record{Project: "p", Provider: "synthetic", SourceInstance: "source", SessionID: "s", MessageID: "m", Text: "needle", ConsentEpoch: 1}
			var envelope archive.Envelope
			isSource := phase == "reserved" || phase == "accepted" || phase == "projected" || phase == "committed" || phase == "proof-mismatch" || phase == "corrupt-data"
			if isSource {
				if e := f.ctl.WithArchiveTransaction(op, "p", func(tx *control.ArchiveTransaction) error {
					var e error
					event := time.Date(2026, 1, 1, 0, 0, 0, 123, time.UTC)
					envelope, e = tx.Reserve(record, &event, false)
					if e != nil {
						return e
					}
					if phase == "reserved" {
						return nil
					}
					if _, e = f.intake.AcceptEnvelope(envelope); e != nil {
						return e
					}
					if phase == "accepted" {
						return nil
					}
					if e = f.source.PutEnvelope(envelope); e != nil {
						return e
					}
					if phase == "committed" || phase == "proof-mismatch" {
						crash := errors.New("fixture crash after control commit")
						e = tx.Complete(record, func(expected archive.Envelope) error { return nil }, func() error { return crash })
						if !errors.Is(e, crash) {
							return fmt.Errorf("crash boundary not reached: %v", e)
						}
					}
					return nil
				}); e != nil {
					t.Fatal(e)
				}
			}
			projection := ""
			if strings.HasPrefix(phase, "projection-") {
				if e := f.ctl.WithArchiveTransaction(op, "p", func(tx *control.ArchiveTransaction) error {
					c, found, e := f.index.Checkpoint("p")
					if e != nil {
						return e
					}
					if !found {
						return search.ErrCheckpoint
					}
					desired := c
					desired.ProjectionGeneration = "retry-generation"
					desired.Complete = false
					projection = desired.ProjectionGeneration
					operation := control.ArchiveProjection{Action: "rebuild", Expected: c, Desired: desired}
					if e = tx.ReserveProjection(operation, 4096); e != nil {
						return e
					}
					if phase == "projection-after" {
						return f.index.BeginRebuild(desired, c.ProjectionGeneration)
					}
					return nil
				}); e != nil {
					t.Fatal(e)
				}
			}
			if phase == "proof-mismatch" {
				if _, e := f.source.Purge("p", "s"); e != nil {
					t.Fatal(e)
				}
			}
			beforeState, _, stateErr := f.ctl.ArchiveState("p")
			if stateErr != nil {
				t.Fatal(stateErr)
			}
			beforePending := f.ctl.Budget().Snapshot().Pending
			f.closeWriter(t)
			var corruptBytes []byte
			if phase == "corrupt-data" {
				path := filepath.Join(f.state, "ingest", "wal", "data")
				corruptBytes = readFile(t, path)
				corruptBytes[0] ^= 1
				if e := os.WriteFile(path, corruptBytes, 0600); e != nil {
					t.Fatal(e)
				}
			}
			missing := ""
			if strings.HasPrefix(phase, "missing-") {
				missing = filepath.Join(f.state, "ingest", "wal", strings.TrimPrefix(phase, "missing-"))
				if phase == "missing-directory" {
					missing = filepath.Join(f.state, "ingest", "wal")
					if e := os.RemoveAll(missing); e != nil {
						t.Fatal(e)
					}
				} else if e := os.Remove(missing); e != nil {
					t.Fatal(e)
				}
			}
			if phase == "projection-disabled" {
				f.cfg.PostgresEnabled = false
				f.writeConfig(t)
			}
			if missing != "" || phase == "proof-mismatch" || phase == "projection-disabled" || phase == "corrupt-data" {
				f.refuse(t, bin)
				if missing != "" {
					if _, e := os.Stat(missing); !os.IsNotExist(e) {
						t.Fatal("missing evidence recreated", e)
					}
				}
				d, e := control.Open(f.state)
				if e != nil {
					t.Fatal(e)
				}
				afterState, _, e := d.ArchiveState("p")
				if e != nil || !reflect.DeepEqual(beforeState, afterState) {
					t.Fatal("failed startup changed pending authority", e)
				}
				d.Close()
				ledger, e := budget.Open(filepath.Join(f.state, "budget.bin"), nil)
				if e != nil {
					t.Fatal(e)
				}
				if !reflect.DeepEqual(ledger.Snapshot().Pending, beforePending) {
					t.Fatal("failed startup released liability")
				}
				ledger.Close()
				if phase == "corrupt-data" && !bytes.Equal(readFile(t, filepath.Join(f.state, "ingest", "wal", "data")), corruptBytes) {
					t.Fatal("corrupt accepted evidence rewritten")
				}
				if phase == "proof-mismatch" {
					_, found, e := f.source.LookupEnvelope(record)
					if e != nil || found {
						t.Fatal("missing committed source resurrected", e)
					}
				}
				return
			}
			addr, stop := f.start(t, bin)
			if phase == "clean" {
				event := time.Date(2026, 1, 1, 0, 0, 0, 123, time.UTC)
				raw, _ := json.Marshal(map[string]any{"project": "p", "provider": "synthetic", "source_instance": "source", "messages": []map[string]any{{"session_id": "s", "message_id": "m", "text": "needle", "source_event_time": event}}})
				req, _ := http.NewRequest("POST", "http://"+addr+"/v1/capture", bytes.NewReader(raw))
				req.Header.Set("X-Operator-Secret", "smoke-secret")
				client := http.Client{Timeout: 3 * time.Second}
				resp, e := client.Do(req)
				if e != nil {
					t.Fatal(e)
				}
				resp.Body.Close()
				if resp.StatusCode != 200 {
					t.Fatal("completed metadata capture", resp.StatusCode)
				}
				var found bool
				envelope, found, e = f.source.LookupEnvelope(record)
				if e != nil || !found || envelope.Metadata.CapturedAt == nil || envelope.Metadata.SourceEventTime == nil || !envelope.Metadata.SourceEventTime.Equal(event) {
					t.Fatal("new capture metadata", e)
				}
			}
			if isSource {
				got, found, e := f.source.LookupEnvelope(record)
				if e != nil {
					t.Fatal(e)
				}
				if phase == "reserved" {
					if found {
						t.Fatal("unaccepted source invented")
					}
				} else {
					a, _ := archive.EncodeEnvelope(got)
					b, _ := archive.EncodeEnvelope(envelope)
					if !found || !bytes.Equal(a, b) {
						t.Fatal("recovery changed identity/metadata")
					}
				}
			}
			deadline := time.Now().Add(5 * time.Second)
			for {
				code, b := metadataGet(t, addr, "/v1/archive/freshness?project=p")
				if code == 200 && b["index_state"] == "caught_up" {
					break
				}
				if time.Now().After(deadline) {
					t.Fatal("checkpoint not recovered", code, b)
				}
				time.Sleep(20 * time.Millisecond)
			}
			if projection != "" {
				c, found, e := f.index.Checkpoint("p")
				if e != nil || !found || c.ProjectionGeneration != projection {
					t.Fatal("projection token changed", c, e)
				}
			}
			stop()
			d, e := control.Open(f.state)
			if e != nil {
				t.Fatal(e)
			}
			env, e := budgetenv.Open(f.state, &f.cfg)
			if e != nil {
				t.Fatal(e)
			}
			if e = d.AttachBudget(env.DetachLedger()); e != nil {
				t.Fatal(e)
			}
			if len(d.Budget().Snapshot().Pending) != 0 {
				t.Fatal("recovered ledger not clear")
			}
			d.Close()
			env.Close()
			addr, stop = f.start(t, bin)
			code, b := metadataGet(t, addr, "/v1/search/query?project=p&q=needle")
			expected := 0
			if (isSource && phase != "reserved") || phase == "clean" {
				expected = 1
			}
			if code != 200 || len(b["hits"].([]any)) != expected {
				t.Fatal("restart retrieval", code, b)
			}
			if phase == "clean" {
				got, found, e := f.source.LookupEnvelope(record)
				a, _ := archive.EncodeEnvelope(got)
				b, _ := archive.EncodeEnvelope(envelope)
				if e != nil || !found || !bytes.Equal(a, b) {
					t.Fatal("restart changed capture metadata", e)
				}
			}
			stop()
		})
	}
}
