//go:build integration

package archive_test

import (
	"aifactory.local/storage/internal/archive"
	"context"
	"fmt"
	"go.mongodb.org/mongo-driver/mongo"
	"go.mongodb.org/mongo-driver/mongo/options"
	"os"
	"testing"
	"time"
)

func TestMongoEnvelopeProjectionAndMigration(t *testing.T) {
	uri := os.Getenv("MONGO_URI")
	if uri == "" {
		t.Skip("MONGO_URI unset: real Mongo NOT_TESTED")
	}
	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()
	db := fmt.Sprintf("envelope_itest_%d", time.Now().UnixNano())
	s, err := archive.OpenMongo(ctx, uri, db, "archive")
	if err != nil {
		t.Fatal(err)
	}
	defer s.Close()
	client, err := mongo.Connect(ctx, options.Client().ApplyURI(uri))
	if err != nil {
		t.Fatal(err)
	}
	defer client.Disconnect(context.Background())
	defer client.Database(db).Drop(context.Background())
	r := archive.Record{Project: "budget-p", SessionID: "s", MessageID: "m", Text: "immutable"}
	if err := s.Put(r); err != nil {
		t.Fatal(err)
	}
	before, err := s.LogicalBytes(ctx, 1<<30)
	if err != nil {
		t.Fatal(err)
	}
	if err := s.AttachMetadata(archive.Envelope{Version: 2, Record: r, Metadata: archive.Metadata{Generation: "g", Ordinal: 1, Legacy: true}}); err != nil {
		t.Fatal(err)
	}
	if _, err := s.LogicalBytes(ctx, before); err == nil {
		t.Fatal("metadata escaped logical budget")
	}
	after, err := s.LogicalBytes(ctx, 1<<30)
	if err != nil || after <= before {
		t.Fatal(after, before, err)
	}
	if ready, err := s.MetadataSchemaReady(); err != nil || ready {
		t.Fatal("uncreated schema", ready, err)
	}
	if err := s.EnsureMetadataSchema(); err != nil {
		t.Fatal(err)
	}
	if err := s.EnsureMetadataSchema(); err != nil {
		t.Fatal("schema retry", err)
	}
	if ready, err := s.MetadataSchemaReady(); err != nil || !ready {
		t.Fatal("created schema", ready, err)
	}
	testEnvelopeScan(t, s)
	testEnvelopeProjection(t, s)
	testMetadataMigration(t, s, s)
	// Reopening must preserve exact nanoseconds and payload, not BSON millisecond rounding.
	reopened, err := archive.OpenMongo(ctx, uri, db, "archive")
	if err != nil {
		t.Fatal(err)
	}
	defer reopened.Close()
	e, found, err := reopened.LookupEnvelope(archive.Record{Project: "metadata-p", SourceInstance: "source", SessionID: "session", MessageID: "message"})
	if err != nil || !found || e.Metadata.CapturedAt == nil || e.Metadata.CapturedAt.Nanosecond() != 123456789 {
		t.Fatal(e, found, err)
	}
}
