package archive

import (
	"context"
	"encoding/json"
	"errors"
	"go.mongodb.org/mongo-driver/bson"
	"go.mongodb.org/mongo-driver/mongo"
	"go.mongodb.org/mongo-driver/mongo/options"
)

func (s *MongoStore) Lookup(r Record) (Record, bool, error) {
	ctx, cancel := context.WithTimeout(context.Background(), s.opTimeout)
	defer cancel()
	var d mongoDoc
	err := s.coll.FindOne(ctx, bson.M{"_id": idOf(r)}).Decode(&d)
	if errors.Is(err, mongo.ErrNoDocuments) {
		return Record{}, false, nil
	}
	if err != nil {
		return Record{}, false, err
	}
	return d.toRecord(), true, nil
}
func (s *MongoStore) Scan(project string, after *Position) (Window, error) {
	ctx, cancel := context.WithTimeout(context.Background(), s.opTimeout)
	defer cancel()
	filter := bson.M{"project": project}
	fields := []string{"session_id", "seq", "source_instance", "message_id"}
	order := bson.D{{Key: "project", Value: 1}}
	for _, f := range fields {
		order = append(order, bson.E{Key: f, Value: 1})
	}
	if after != nil {
		values := []any{after.SessionID, after.Seq, after.SourceInstance, after.MessageID}
		ors := bson.A{}
		for n, f := range fields {
			term := bson.M{f: bson.M{"$gt": values[n]}}
			for k := 0; k < n; k++ {
				term[fields[k]] = values[k]
			}
			ors = append(ors, term)
		}
		filter["$or"] = ors
	}
	cur, err := s.coll.Find(ctx, filter, options.Find().SetSort(order).SetHint("archive_page_v1").SetLimit(ScanRecords+1).SetBatchSize(32).SetMaxTime(s.opTimeout))
	if err != nil {
		return Window{}, err
	}
	defer cur.Close(ctx)
	w := Window{}
	size := 0
	for cur.Next(ctx) {
		var d mongoDoc
		if err := cur.Decode(&d); err != nil {
			return Window{}, err
		}
		r := d.toRecord()
		b, _ := json.Marshal(r)
		if len(w.Records) == ScanRecords || size+len(b) > ScanBytes {
			if len(w.Records) == 0 {
				return Window{}, ErrRecordTooLarge
			}
			w.More = true
			break
		}
		size += len(b)
		w.Records = append(w.Records, r)
	}
	if err := cur.Err(); err != nil {
		return Window{}, err
	}
	return w, nil
}
