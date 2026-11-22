//go:build integration

package workflow

import (
	"context"
	"testing"
)

// The per-row inventory must equal a full LogicalBytes read after every kind of change,
// including maintenance that rewrites tuples and a schema upgrade mid-life.
func TestInventoryEqualsFullReadThroughEveryChange(t *testing.T) {
	s, _ := isolatedArchiveSchema(t)
	ctx := context.Background()
	var inv *Inventory
	check := func(step string) {
		t.Helper()
		full, err := s.LogicalBytes(ctx, 1<<40)
		if err != nil {
			t.Fatal(step, "full", err)
		}
		next, err := s.Inventory(ctx, 1<<40, inv)
		if err != nil {
			t.Fatal(step, "inventory", err)
		}
		fresh, err := s.Inventory(ctx, 1<<40, nil)
		if err != nil || next.Total != full || fresh.Total != full {
			t.Fatalf("%s: incremental %d, rebuilt %v, full %d (%v)", step, next.Total, fresh, full, err)
		}
		inv = next
	}
	exec := func(sql string) {
		t.Helper()
		if _, err := s.pool.Exec(ctx, sql); err != nil {
			t.Fatal(sql, err)
		}
	}
	check("empty")
	exec(`INSERT INTO workflow_tasks VALUES('p','t1',1,'{"a":"b"}'),('p','t2',1,'{"c":"d"}'),('p,t','1',1,'{}')`)
	exec(`INSERT INTO archive_index VALUES('k1','ph','p','i1','x',to_tsvector('simple','alpha beta')),('k2','ph','p','i2','y',to_tsvector('simple','gamma')),('k3','ph','p','i3','z',to_tsvector('simple','delta'))`)
	check("inserts")
	exec(`UPDATE archive_index SET terms=to_tsvector('simple','a much longer replacement text') WHERE key_hash='k2'`)
	exec(`UPDATE workflow_tasks SET version=2, fields='{"a":"bbbbbbbb"}' WHERE id='t1'`)
	check("updates")
	exec(`DELETE FROM archive_index WHERE key_hash='k3'`)
	check("delete")
	exec(`INSERT INTO document_index VALUES('d1','ph','p','di','{"x":[1,2,3]}')`)
	check("document")
	if err := s.UpgradeArchiveMetadata(ctx); err != nil {
		t.Fatal(err)
	}
	check("metadata schema upgrade mid-life")
	exec(`INSERT INTO archive_index(key_hash,project_hash,project,identity,payload_hash,terms,metadata_hash,source_generation,source_ordinal) VALUES('k4','ph','p','i4','w',to_tsvector('simple','meta'),repeat('a',64),'g',1)`)
	exec(`INSERT INTO archive_checkpoint VALUES('ph','p','g','proj','0',1,false)`)
	check("metadata rows")
	exec(`UPDATE archive_checkpoint SET ordinal=2, complete=true`)
	check("checkpoint update")
	exec(`VACUUM FREEZE archive_index`)
	check("vacuum freeze")
	exec(`VACUUM FULL archive_index`)
	check("vacuum full")
	exec(`CLUSTER archive_index USING archive_index_pkey`)
	check("cluster")
	exec(`TRUNCATE archive_index`)
	check("truncate")
	// The schema forbids this row; drop its guard here to prove the code refuses it as well.
	exec(`ALTER TABLE archive_index DROP CONSTRAINT archive_metadata_shape`)
	exec(`INSERT INTO archive_index(key_hash,project_hash,project,identity,payload_hash,terms,source_generation) VALUES('k5','ph','p','i5','v',to_tsvector('simple','bad'),'g')`)
	if _, err := s.LogicalBytes(ctx, 1<<40); err == nil {
		t.Fatal("full read accepted an unversioned metadata row")
	}
	if _, err := s.Inventory(ctx, 1<<40, inv); err == nil {
		t.Fatal("incremental pass accepted an unversioned metadata row")
	}
	exec(`DELETE FROM archive_index WHERE key_hash='k5'`)
	check("after removing the bad row")
	if _, err := s.Inventory(ctx, inv.Total-1, inv); err == nil {
		t.Fatal("incremental pass escaped the cap")
	}
}
