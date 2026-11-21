package archive

import (
	"bytes"
	"context"
	"fmt"

	"aifactory.local/storage/internal/logical"
	"go.mongodb.org/mongo-driver/bson"
	"go.mongodb.org/mongo-driver/mongo/options"
)

// SchemaLogicalBytes reserves the versioned collection and index definitions even
// before creation. Physical allocator blocks and the database journal are excluded.
func SchemaLogicalBytes() int64 {
	return int64(len(`logical-v1:archive:compound_id(p,si,s,m);project_session_seq(project,session_id,seq);archive_page_v1(project,session_id,seq,source_instance,message_id);archive_metadata_v2_order(project,archive_metadata.generation,archive_metadata.ordinal):unique:partial_metadata_exists`))
}

// LogicalBytes streams canonical managed records with a bounded cursor. Unknown
// fields or an inconsistent identity refuse rather than disappear from billing.
func (s *MongoStore) LogicalBytes(ctx context.Context, limit int64) (int64, error) {
	ctx, cancel := context.WithTimeout(ctx, s.opTimeout)
	defer cancel()
	total := SchemaLogicalBytes()
	if total > limit {
		return 0, fmt.Errorf("archive: logical inventory exceeds cap")
	}
	cursor, e := s.coll.Find(ctx, bson.D{}, options.Find().SetBatchSize(100))
	if e != nil {
		return 0, e
	}
	defer cursor.Close(ctx)
	for cursor.Next(ctx) {
		var doc mongoDoc
		if e = cursor.Decode(&doc); e != nil {
			return 0, e
		}
		canonical, e := bson.Marshal(doc)
		if e != nil {
			return 0, e
		}
		// Canonical writes are stable BSON; refuse unmanaged fields or changed types.
		if !bytes.Equal(canonical, cursor.Current) || doc.ID != idOf(doc.toRecord()) {
			return 0, fmt.Errorf("archive: unknown logical representation")
		}
		if doc.Metadata != nil {
			if _, e = doc.envelope(); e != nil {
				return 0, e
			}
		}
		total, e = logical.Add(total, documentReservationBytes(doc), limit)
		if e != nil {
			return 0, e
		}
	}
	return total, cursor.Err()
}
