//go:build integration

package workflow

import (
	"context"
	"testing"
)

func TestMetadataInventoryChargesRowsAndCheckpoint(t *testing.T) {
	s, _ := isolatedArchiveSchema(t)
	ctx := context.Background()
	if err := s.UpgradeArchiveMetadata(ctx); err != nil {
		t.Fatal(err)
	}
	before, err := s.LogicalBytes(ctx, 1<<30)
	if err != nil || before < SchemaLogicalBytes() {
		t.Fatal("schema inventory missing", before, err)
	}
	_, err = s.pool.Exec(ctx, `INSERT INTO archive_index(key_hash,project_hash,project,identity,payload_hash,terms,metadata_hash,source_generation,source_ordinal) VALUES('key','ph','p','identity','payload',to_tsvector('simple','content'),repeat('a',64),'source',1)`)
	if err != nil {
		t.Fatal(err)
	}
	row, err := s.LogicalBytes(ctx, 1<<30)
	if err != nil || row <= before {
		t.Fatal("metadata row uncharged", row, before, err)
	}
	if _, err := s.LogicalBytes(ctx, before); err == nil {
		t.Fatal("metadata escaped cap")
	}
	_, err = s.pool.Exec(ctx, `INSERT INTO archive_checkpoint VALUES('ph','p','source','projection','0',1,true)`)
	if err != nil {
		t.Fatal(err)
	}
	checkpoint, err := s.LogicalBytes(ctx, 1<<30)
	if err != nil || checkpoint <= row {
		t.Fatal("checkpoint uncharged", checkpoint, row, err)
	}
	if _, err := s.LogicalBytes(ctx, row); err == nil {
		t.Fatal("checkpoint escaped cap")
	}
}
