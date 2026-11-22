package archive

import (
	"bytes"
	"context"
	"fmt"

	"aifactory.local/storage/internal/logical"
	"go.mongodb.org/mongo-driver/bson"
	"go.mongodb.org/mongo-driver/mongo/options"
)

type docState struct {
	metadata string // raw archive_metadata: the only field a stored document can change
	cost     int64
}

// Inventory is a logical archive inventory remembered per document, so a later
// pass only rereads new documents and documents whose archive_metadata changed.
// Documents change in no other way through this code (Put, PutEnvelope,
// AttachMetadata, Purge); a full LogicalBytes read remains the periodic check.
type Inventory struct {
	Total int64
	docs  map[string]docState
}

// inventoryRead validates one full document exactly as LogicalBytes does and bills it.
func inventoryRead(raw bson.Raw) (string, docState, error) {
	var doc mongoDoc
	if e := bson.Unmarshal(raw, &doc); e != nil {
		return "", docState{}, e
	}
	canonical, e := bson.Marshal(doc)
	if e != nil {
		return "", docState{}, e
	}
	if !bytes.Equal(canonical, raw) || doc.ID != idOf(doc.toRecord()) {
		return "", docState{}, fmt.Errorf("archive: unknown logical representation")
	}
	if doc.Metadata != nil {
		if _, e = doc.envelope(); e != nil {
			return "", docState{}, e
		}
	}
	id := string(raw.Lookup("_id").Value)
	metadata := ""
	if v, err := raw.LookupErr("archive_metadata"); err == nil {
		metadata = string(v.Value)
	}
	return id, docState{metadata: metadata, cost: documentReservationBytes(doc)}, nil
}

// Inventory builds (prev == nil) or refreshes the per-document inventory. Any
// error returns no inventory, so the caller cannot keep a half-merged one.
func (s *MongoStore) Inventory(ctx context.Context, limit int64, prev *Inventory) (*Inventory, error) {
	ctx, cancel := context.WithTimeout(ctx, s.opTimeout)
	defer cancel()
	next := &Inventory{docs: map[string]docState{}}
	if prev == nil {
		cursor, e := s.coll.Find(ctx, bson.D{}, options.Find().SetBatchSize(100))
		if e != nil {
			return nil, e
		}
		defer cursor.Close(ctx)
		for cursor.Next(ctx) {
			id, state, e := inventoryRead(cursor.Current)
			if e != nil {
				return nil, e
			}
			next.docs[id] = state
		}
		if e = cursor.Err(); e != nil {
			return nil, e
		}
		return next.finish(limit)
	}
	var stale []bson.RawValue
	probe, e := s.coll.Find(ctx, bson.D{}, options.Find().SetProjection(bson.D{{Key: "archive_metadata", Value: 1}}).SetBatchSize(1000))
	if e != nil {
		return nil, e
	}
	for probe.Next(ctx) {
		raw := probe.Current.Lookup("_id")
		// Own copy: the id outlives this cursor batch.
		idValue := bson.RawValue{Type: raw.Type, Value: append([]byte(nil), raw.Value...)}
		id := string(idValue.Value)
		metadata := ""
		if v, err := probe.Current.LookupErr("archive_metadata"); err == nil {
			metadata = string(v.Value)
		}
		if was, ok := prev.docs[id]; ok && was.metadata == metadata {
			next.docs[id] = was
		} else {
			stale = append(stale, idValue)
		}
	}
	e = probe.Err()
	probe.Close(ctx)
	if e != nil {
		return nil, e
	}
	for start := 0; start < len(stale); start += 500 {
		end := min(start+500, len(stale))
		if e = s.rereadInventory(ctx, stale[start:end], next); e != nil {
			return nil, e
		}
	}
	return next.finish(limit)
}

func (inv *Inventory) finish(limit int64) (*Inventory, error) {
	if e := inv.total(limit); e != nil {
		return nil, e
	}
	return inv, nil
}

func (s *MongoStore) rereadInventory(ctx context.Context, ids []bson.RawValue, next *Inventory) error {
	cursor, e := s.coll.Find(ctx, bson.D{{Key: "_id", Value: bson.D{{Key: "$in", Value: ids}}}}, options.Find().SetBatchSize(100))
	if e != nil {
		return e
	}
	defer cursor.Close(ctx)
	for cursor.Next(ctx) {
		id, state, e := inventoryRead(cursor.Current)
		if e != nil {
			return e
		}
		next.docs[id] = state
	}
	return cursor.Err()
}

// total sums every remembered document after the schema charge, bounded by limit.
// A document deleted between the probe and the reread is simply not billed, as a
// fresh full read would not bill it either.
func (inv *Inventory) total(limit int64) error {
	total := SchemaLogicalBytes()
	if total > limit {
		return fmt.Errorf("archive: logical inventory exceeds cap")
	}
	var e error
	for _, d := range inv.docs {
		if d.cost < 0 {
			return fmt.Errorf("archive: negative logical cost")
		}
		if total, e = logical.Add(total, d.cost, limit); e != nil {
			return e
		}
	}
	inv.Total = total
	return nil
}
