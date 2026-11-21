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

func TestMongoSummarySourceUsesExistingMetadataSchema(t *testing.T) {
	uri := os.Getenv("MONGO_URI")
	if uri == "" {
		t.Skip("MONGO_URI unset: actual Mongo summary contract NOT_TESTED")
	}
	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()
	db := fmt.Sprintf("summary_itest_%d", time.Now().UnixNano())
	client, e := mongo.Connect(ctx, options.Client().ApplyURI(uri))
	if e != nil {
		t.Fatal(e)
	}
	defer client.Disconnect(context.Background())
	defer client.Database(db).Drop(context.Background())
	store, e := archive.OpenMongo(ctx, uri, db, "archive")
	if e != nil {
		t.Fatal(e)
	}
	defer store.Close()
	if ready, e := store.MetadataSchemaReady(); e != nil || ready {
		t.Fatal("unexpected schema before explicit preparation", ready, e)
	}
	if e = store.EnsureMetadataSchema(); e != nil {
		t.Fatal(e)
	}
	testSummarySourceContract(t, store)
	testSummarySourceIgnoresLegacyInputs(t, store)
	testSummarySourceUnicodeAndCompletePages(t, store)
	at := time.Date(2026, 1, 1, 0, 0, 0, 123456789, time.UTC)
	original := archive.Envelope{Version: 2, Record: archive.Record{Project: "derived-roundtrip", Provider: "v", SourceInstance: "i", SessionID: "s", MessageID: "marked", Type: archive.TypeSummary, Role: "assistant", Text: "fixture", ConsentEpoch: 1}, Metadata: archive.Metadata{Generation: "g", Ordinal: 1, CapturedAt: &at, DerivedKind: archive.DerivedSessionExtract}}
	if e = store.PutEnvelope(original); e != nil {
		t.Fatal(e)
	}
	reopened, e := archive.OpenMongo(ctx, uri, db, "archive")
	if e != nil {
		t.Fatal(e)
	}
	defer reopened.Close()
	actual, found, e := reopened.LookupEnvelope(original.Record)
	if e != nil || !found || actual.Record != original.Record || actual.Metadata.DerivedKind != archive.DerivedSessionExtract || actual.Metadata.CapturedAt == nil || !actual.Metadata.CapturedAt.Equal(at) {
		t.Fatal("Mongo marker/nanosecond/identity roundtrip", actual, e)
	}
}
