//go:build integration

package archive

import (
	"context"
	"testing"

	"go.mongodb.org/mongo-driver/bson"
)

// The per-document inventory must equal a full LogicalBytes read after every write
// path this package has, and must refuse a malformed new document like the full read.
func TestInventoryEqualsFullReadThroughEveryWrite(t *testing.T) {
	s := newMongoStore(t)
	ctx := context.Background()
	var inv *Inventory
	check := func(step string) {
		t.Helper()
		full, err := s.LogicalBytes(ctx, 1<<40)
		if err != nil {
			t.Fatal(step, "full", err)
		}
		next, err := s.Inventory(ctx, 1<<40, inv)
		if err != nil || next.Total != full {
			t.Fatalf("%s: incremental %v, full %d (%v)", step, next, full, err)
		}
		inv = next
	}
	check("empty")
	for i, m := range []string{"m1", "m2", "m3"} {
		r := rec("p", "s", m, "text")
		r.Seq = i + 1
		if err := s.Put(r); err != nil {
			t.Fatal(err)
		}
	}
	check("puts")
	r := rec("p", "s", "m2", "text")
	r.Seq = 2
	if err := s.AttachMetadata(Envelope{Version: 2, Record: r, Metadata: Metadata{Generation: "g", Ordinal: 1, Legacy: true}}); err != nil {
		t.Fatal(err)
	}
	check("attach metadata")
	e := Envelope{Version: 2, Record: rec("p", "s2", "m9", "enveloped"), Metadata: Metadata{Generation: "g", Ordinal: 2, Legacy: true}}
	if err := s.PutEnvelope(e); err != nil {
		t.Fatal(err)
	}
	check("put envelope")
	if _, err := s.Purge("p", "s2"); err != nil {
		t.Fatal(err)
	}
	check("purge session")
	bad := toDoc(rec("p", "s3", "m1", "x"))
	raw, _ := bson.Marshal(bad)
	var extra bson.D
	_ = bson.Unmarshal(raw, &extra)
	extra = append(extra, bson.E{Key: "unmanaged", Value: 1})
	if _, err := s.coll.InsertOne(ctx, extra); err != nil {
		t.Fatal(err)
	}
	if _, err := s.Inventory(ctx, 1<<40, inv); err == nil {
		t.Fatal("incremental pass billed an unknown document representation")
	}
	if _, err := s.coll.DeleteOne(ctx, bson.D{{Key: "unmanaged", Value: 1}}); err != nil {
		t.Fatal(err)
	}
	check("after removing the unknown document")
	// Known limit: a body change outside this package is seen only by the full read.
	if _, err := s.coll.UpdateOne(ctx, bson.D{{Key: "message_id", Value: "m1"}}, bson.D{{Key: "$set", Value: bson.D{{Key: "text", Value: "changed outside the store, much longer"}}}}); err != nil {
		t.Fatal(err)
	}
	full, _ := s.LogicalBytes(ctx, 1<<40)
	stale, err := s.Inventory(ctx, 1<<40, inv)
	if err != nil || stale.Total == full {
		t.Fatalf("documented limit changed: incremental %v full %d (%v)", stale, full, err)
	}
	rebuilt, err := s.Inventory(ctx, 1<<40, nil)
	if err != nil || rebuilt.Total != full {
		t.Fatalf("full rebuild must see an out-of-band change: %v %d (%v)", rebuilt, full, err)
	}
	if _, err := s.Inventory(ctx, rebuilt.Total-1, rebuilt); err == nil {
		t.Fatal("incremental pass escaped the cap")
	}
}
