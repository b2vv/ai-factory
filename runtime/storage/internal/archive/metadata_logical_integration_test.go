//go:build integration

package archive

import (
	"context"
	"testing"
)

func TestLogicalInventoryRejectsMalformedMetadata(t *testing.T) {
	s := newMongoStore(t)
	d := toDoc(rec("p", "s", "m", "preserve"))
	d.Metadata = &metadataDoc{Version: 99, Generation: "g", Ordinal: 1, Legacy: true}
	if _, err := s.coll.InsertOne(context.Background(), d); err != nil {
		t.Fatal(err)
	}
	if _, err := s.LogicalBytes(context.Background(), 1<<30); err == nil {
		t.Fatal("malformed metadata accepted as billable canonical source")
	}
}
