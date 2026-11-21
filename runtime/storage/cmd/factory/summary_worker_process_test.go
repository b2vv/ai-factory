//go:build integration

package main

import (
	"aifactory.local/storage/internal/archive"
	"aifactory.local/storage/internal/registry"
	"aifactory.local/storage/internal/summary"
	"aifactory.local/storage/internal/wal"
	"bytes"
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"go.mongodb.org/mongo-driver/bson"
	"go.mongodb.org/mongo-driver/mongo"
	"go.mongodb.org/mongo-driver/mongo/options"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

// Optional prebuilt mode is explicit and hash-bound. The runner records source
// bindings and performs the offline linux/amd64 build, rather than pretending a
// compiler exists in the minimal runtime image. Normal builder/CI keeps go build.
func summaryFactoryBinary(t *testing.T) string {
	t.Helper()
	path := os.Getenv("SUMMARY_FACTORY_BINARY")
	if path == "" {
		return buildFactory(t, t.TempDir())
	}
	stat, err := os.Lstat(path)
	if err != nil || !stat.Mode().IsRegular() || stat.Mode().Perm()&0111 == 0 {
		t.Fatal("invalid prebuilt factory fixture", err)
	}
	raw, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}
	hash := sha256.Sum256(raw)
	if hex.EncodeToString(hash[:]) != os.Getenv("SUMMARY_FACTORY_SHA256") {
		t.Fatal("prebuilt fixture hash mismatch")
	}
	return path
}

func TestProcessSessionExtractWorkerIsOptInAndRestartSafe(t *testing.T) {
	f := metadataFixture(t)
	if _, err := f.ctl.SetConsent(registry.Principal{Kind: registry.Operator}, "p", "synthetic", "summary", true); err != nil {
		t.Fatal(err)
	}
	proxy, blocked, rejected := metadataInsertFaultProxy(t, f.cfg.MongoURI)
	f.cfg.MongoURI = proxy
	f.writeConfig(t)
	f.closeWriter(t)
	bin := summaryFactoryBinary(t)
	options := []string{"-extract-idle-after", "1ns", "-extract-poll", "20ms"}
	addr, stop := f.start(t, bin, options...)
	raw, _ := json.Marshal(map[string]any{"project": "p", "provider": "synthetic", "source_instance": "source", "messages": []map[string]any{{"session_id": "s", "message_id": "m", "role": "user", "text": "worker local source needle"}}})
	req, _ := http.NewRequest("POST", "http://"+addr+"/v1/capture", bytes.NewReader(raw))
	req.Header.Set("X-Operator-Secret", "smoke-secret")
	response, err := (&http.Client{Timeout: 10 * time.Second}).Do(req)
	if err != nil {
		t.Fatal(err)
	}
	response.Body.Close()
	if response.StatusCode != 200 {
		t.Fatal("synthetic original capture", response.StatusCode)
	}
	records, err := f.source.Fetch("p")
	if err != nil || len(records) != 1 || records[0].Type != archive.TypeMessage {
		t.Fatal("default-off source changed", len(records), err)
	}
	// Observe more than one configured poll interval, not a single immediate read.
	quietUntil := time.Now().Add(200 * time.Millisecond)
	for time.Now().Before(quietUntil) {
		records, err = f.source.Fetch("p")
		if err != nil || len(records) != 1 || records[0].Type != archive.TypeMessage {
			t.Fatal("default-off worker published during quiet window", len(records), err)
		}
		code, view := metadataOperatorHealth(t, addr)
		if code != 200 || view["session_extracts"] != nil {
			t.Fatal("default-off worker enabled in health", code, view)
		}
		time.Sleep(20 * time.Millisecond)
	}
	stop()
	enabled := append([]string{"-session-extracts"}, options...)
	blocked.Store(true)
	addr, stop = f.start(t, bin, enabled...)
	deadline := time.Now().Add(15 * time.Second)
	for rejected.Load() == 0 {
		if time.Now().After(deadline) {
			t.Fatal("derived insert outage was not reached")
		}
		time.Sleep(50 * time.Millisecond)
	}
	// No producer retry: stop with the first body durable in WAL but absent in
	// Mongo. The next real process must reuse that exact envelope on startup.
	stop()
	frames, report, err := wal.AcceptedWithin(filepath.Join(f.state, "ingest", "wal"), f.cfg.WALBytes)
	if err != nil || report.IsBlocked() || report.TruncateAt >= 0 {
		t.Fatal("accepted fixture WAL unavailable", err)
	}
	var durable archive.Envelope
	for _, frame := range frames {
		e, err := archive.DecodeEnvelope(frame.Version, frame.Payload)
		if err != nil {
			t.Fatal(err)
		}
		if e.Metadata.DerivedKind == archive.DerivedSessionExtract {
			durable = e
		}
	}
	if durable.Record.MessageID == "" {
		t.Fatal("failed process did not retain first derived body")
	}
	blocked.Store(false)
	addr, stop = f.start(t, bin, enabled...)
	var accepted archive.Record
	deadline = time.Now().Add(15 * time.Second)
	for {
		records, err = f.source.Fetch("p")
		if err != nil {
			t.Fatal(err)
		}
		for _, r := range records {
			if r.Type == archive.TypeSummary {
				accepted = r
			}
		}
		if accepted.MessageID != "" {
			break
		}
		if time.Now().After(deadline) {
			t.Fatal("actual background worker did not publish")
		}
		time.Sleep(50 * time.Millisecond)
	}
	envelope, found, err := f.source.LookupEnvelope(accepted)
	if err != nil || !found {
		t.Fatal(err)
	}
	expectedBytes, _ := archive.EncodeEnvelope(durable)
	actualBytes, _ := archive.EncodeEnvelope(envelope)
	if !bytes.Equal(expectedBytes, actualBytes) {
		t.Fatal("actual restart regenerated the accepted body/time/ordinal")
	}
	proof, sources, err := summary.LoadStored(envelope, f.source, time.Now().UTC())
	if err != nil || len(sources) != 1 || sources[0].Record.MessageID != "m" || proof.Document.Kind != "extractive" || proof.Document.Manifest.CaptureCompleteness != "unknown" || proof.Document.Manifest.Scope.BranchKnown {
		t.Fatal("process published unsupported proof", err)
	}
	deadline = time.Now().Add(10 * time.Second)
	for {
		code, body := metadataGet(t, addr, "/v1/search/query?project=p&sort=recent&time_field=captured_at&q=needle")
		hits, _ := body["hits"].([]any)
		if code == 200 && len(hits) == 2 {
			break
		}
		if time.Now().After(deadline) {
			t.Fatal("actual worker/index pipeline did not become searchable", code)
		}
		time.Sleep(50 * time.Millisecond)
	}
	stop()
	addr, stop = f.start(t, bin, enabled...)
	defer stop()
	// First scoped query after readiness observes the existing accepted source;
	// its exact body must survive restart without a new generation for old inputs.
	path := "/v1/archive/query?project=p&q=needle"
	if code, body := metadataGet(t, addr, path); code != 200 {
		t.Fatal("archive after restart", code)
	} else if hits, _ := body["hits"].([]any); len(hits) != 2 {
		t.Fatal("restart changed source count", len(hits))
	}
	records, err = f.source.Fetch("p")
	if err != nil || len(records) != 2 {
		t.Fatal("restart duplicated generation", len(records), err)
	}
	for _, r := range records {
		if r.Type == archive.TypeSummary && r != accepted {
			t.Fatal("first durable body changed across restart")
		}
	}
}

func TestProcessSessionExtractsRejectMissingMongoAndInvalidPoll(t *testing.T) {
	bin := summaryFactoryBinary(t)
	for _, tc := range []struct {
		name string
		args []string
		want string
	}{
		{"missing-mongo", []string{"-session-extracts"}, "session-extracts requires the enabled Mongo archive"},
		{"zero-poll", []string{"-extract-poll", "0"}, "extract-poll must be positive"},
		{"invalid-plan", []string{"-extract-active-after", "0"}, "summary: invalid configuration"},
		{"invalid-options", []string{"-extract-max-excerpt", "0"}, "summary: invalid extract options"},
		{"negative-poll", []string{"-extract-poll", "-1ns"}, "extract-poll must be positive"},
	} {
		t.Run(tc.name, func(t *testing.T) {
			state := filepath.Join(t.TempDir(), "absent-state")
			ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
			defer cancel()
			args := append([]string{"-state", state}, tc.args...)
			cmd := exec.CommandContext(ctx, bin, args...)
			out, err := cmd.CombinedOutput()
			if ctx.Err() != nil || err == nil || !strings.Contains(string(out), tc.want) {
				t.Fatal("missing startup prerequisite validation", tc.name, err, string(out))
			}
			if _, err = os.Stat(state); !os.IsNotExist(err) {
				t.Fatal("invalid startup modified durable state", err)
			}
		})
	}
}

func metadataOperatorHealth(t *testing.T, addr string) (int, map[string]any) {
	t.Helper()
	req, err := http.NewRequest(http.MethodGet, "http://"+addr+"/health", nil)
	if err != nil {
		t.Fatal(err)
	}
	req.Header.Set("X-Operator-Secret", "smoke-secret")
	response, err := (&http.Client{Timeout: 3 * time.Second}).Do(req)
	if err != nil {
		t.Fatal(err)
	}
	defer response.Body.Close()
	var view map[string]any
	if err = json.NewDecoder(response.Body).Decode(&view); err != nil {
		t.Fatal(err)
	}
	return response.StatusCode, view
}

func TestProcessSessionExtractsRefusesIncompatibleSummarySchemaWithoutDDL(t *testing.T) {
	f := metadataFixture(t)
	f.closeWriter(t)
	ctx, cancel := context.WithTimeout(context.Background(), 15*time.Second)
	defer cancel()
	client, err := mongo.Connect(ctx, options.Client().ApplyURI(f.cfg.MongoURI))
	if err != nil {
		t.Fatal(err)
	}
	defer client.Disconnect(context.Background())
	collection := client.Database(f.cfg.MongoDB).Collection(f.cfg.MongoCollection)
	if _, err = collection.Indexes().DropOne(ctx, "archive_metadata_v2_order"); err != nil {
		t.Fatal(err)
	}
	keys := bson.D{{Key: "project", Value: 1}, {Key: "archive_metadata.generation", Value: 1}, {Key: "archive_metadata.ordinal", Value: 1}}
	if _, err = collection.Indexes().CreateOne(ctx, mongo.IndexModel{Keys: keys, Options: options.Index().SetName("archive_metadata_v2_order").SetUnique(true).SetPartialFilterExpression(bson.M{"archive_metadata": bson.M{"$exists": true}}).SetCollation(&options.Collation{Locale: "en"})}); err != nil {
		t.Fatal(err)
	}
	if ready, err := f.source.MetadataSchemaReady(); err != nil || !ready {
		t.Fatal("legacy-compatible schema fixture invalid", ready, err)
	}
	if ready, err := f.source.SummarySchemaReady(); err == nil || ready {
		t.Fatal("summary incompatible schema fixture invalid", ready, err)
	}
	bin := summaryFactoryBinary(t)
	runCtx, stop := context.WithTimeout(context.Background(), 10*time.Second)
	defer stop()
	out, err := exec.CommandContext(runCtx, bin, "-state", f.state, "-config", f.configPath, "-operator-token", f.token, "-listen", "127.0.0.1:0", "-session-extracts").CombinedOutput()
	if err == nil || runCtx.Err() != nil || strings.Contains(string(out), "LISTEN ") || !strings.Contains(string(out), "summary scope requires simple collation") {
		t.Fatal("incompatible summary schema reached startup or wrong refusal", err, string(out))
	}
	if ready, err := f.source.MetadataSchemaReady(); err != nil || !ready {
		t.Fatal("startup altered legacy metadata schema", ready, err)
	}
	if ready, err := f.source.SummarySchemaReady(); err == nil || ready {
		t.Fatal("startup silently repaired summary schema", ready, err)
	}
}
