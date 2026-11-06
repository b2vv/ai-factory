package archive

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"go.mongodb.org/mongo-driver/bson"
	"go.mongodb.org/mongo-driver/mongo"
	"go.mongodb.org/mongo-driver/mongo/options"
	"time"
)

// Times use canonical RFC3339Nano strings to avoid BSON datetime's millisecond
// truncation. This projection is outside the original Record and identity.
type metadataDoc struct {
	Version         int    `bson:"version"`
	Generation      string `bson:"generation"`
	Ordinal         int64  `bson:"ordinal"`
	CapturedAt      string `bson:"captured_at"`
	SourceEventTime string `bson:"source_event_time"`
	Legacy          bool   `bson:"legacy"`
}

func envelopeDoc(e Envelope) (mongoDoc, error) {
	e, err := canonicalEnvelope(e)
	if err != nil {
		return mongoDoc{}, err
	}
	d := toDoc(e.Record)
	d.Metadata = &metadataDoc{Version: 2, Generation: e.Metadata.Generation, Ordinal: e.Metadata.Ordinal, Legacy: e.Metadata.Legacy}
	if e.Metadata.CapturedAt != nil {
		d.Metadata.CapturedAt = e.Metadata.CapturedAt.Format(time.RFC3339Nano)
	}
	if e.Metadata.SourceEventTime != nil {
		d.Metadata.SourceEventTime = e.Metadata.SourceEventTime.Format(time.RFC3339Nano)
	}
	return d, nil
}
func (d mongoDoc) envelope() (Envelope, error) {
	if d.Metadata == nil {
		return Envelope{Version: 1, Record: d.toRecord(), Metadata: Metadata{Legacy: true}}, nil
	}
	m := d.Metadata
	e := Envelope{Version: m.Version, Record: d.toRecord(), Metadata: Metadata{Generation: m.Generation, Ordinal: m.Ordinal, Legacy: m.Legacy}}
	for _, pair := range []struct {
		raw    string
		target **time.Time
	}{{m.CapturedAt, &e.Metadata.CapturedAt}, {m.SourceEventTime, &e.Metadata.SourceEventTime}} {
		if pair.raw != "" {
			v, err := time.Parse(time.RFC3339Nano, pair.raw)
			if err != nil {
				return Envelope{}, err
			}
			*pair.target = &v
		}
	}
	return canonicalEnvelope(e)
}
func (s *MongoStore) LookupEnvelope(r Record) (Envelope, bool, error) {
	ctx, cancel := context.WithTimeout(context.Background(), s.opTimeout)
	defer cancel()
	var d mongoDoc
	err := s.coll.FindOne(ctx, bson.M{"_id": idOf(r)}).Decode(&d)
	if errors.Is(err, mongo.ErrNoDocuments) {
		return Envelope{}, false, nil
	}
	if err != nil {
		return Envelope{}, false, err
	}
	if d.ID != idOf(d.toRecord()) {
		return Envelope{}, false, ErrIDConflict
	}
	e, err := d.envelope()
	return e, true, err
}
func (s *MongoStore) PutEnvelope(e Envelope) error {
	d, err := envelopeDoc(e)
	if err != nil {
		return err
	}
	ctx, cancel := context.WithTimeout(context.Background(), s.opTimeout)
	defer cancel()
	_, err = s.coll.InsertOne(ctx, d)
	if err == nil {
		s.up.Store(true)
		return nil
	}
	if mongo.IsDuplicateKeyError(err) {
		old, found, readErr := s.LookupEnvelope(e.Record)
		if readErr != nil {
			return readErr
		}
		if found && equalEnvelope(old, e) {
			return nil
		}
		return ErrIDConflict
	}
	s.up.Store(false)
	return err
}

// AttachMetadata is compare-and-set on ALL original fields and missing metadata.
// No upsert: deletion between scan and attachment cannot resurrect a source row.
func (s *MongoStore) AttachMetadata(e Envelope) error {
	d, err := envelopeDoc(e)
	if err != nil {
		return err
	}
	if !e.Metadata.Legacy {
		return ErrIDConflict
	}
	original, _ := bson.Marshal(toDoc(e.Record))
	var filter bson.M
	if err := bson.Unmarshal(original, &filter); err != nil {
		return err
	}
	filter["_id"] = idOf(e.Record)
	filter["archive_metadata"] = bson.M{"$exists": false}
	ctx, cancel := context.WithTimeout(context.Background(), s.opTimeout)
	defer cancel()
	result, err := s.coll.UpdateOne(ctx, filter, bson.M{"$set": bson.M{"archive_metadata": d.Metadata}})
	if err != nil {
		return err
	}
	if result.MatchedCount == 1 {
		return nil
	}
	old, found, err := s.LookupEnvelope(e.Record)
	if err != nil {
		return err
	}
	if found && equalEnvelope(old, e) {
		return nil
	}
	return ErrIDConflict
}

// EnsureMetadataSchema is called only by the exclusive upgrade coordinator,
// after durable control activation and admission; ordinary OpenMongo never calls it.
func (s *MongoStore) EnsureMetadataSchema() error {
	ctx, cancel := context.WithTimeout(context.Background(), s.opTimeout)
	defer cancel()
	_, err := s.coll.Indexes().CreateOne(ctx, mongo.IndexModel{Keys: bson.D{{Key: "project", Value: 1}, {Key: "archive_metadata.generation", Value: 1}, {Key: "archive_metadata.ordinal", Value: 1}}, Options: options.Index().SetName("archive_metadata_v2_order").SetUnique(true).SetPartialFilterExpression(bson.M{"archive_metadata": bson.M{"$exists": true}})})
	return err
}
func (s *MongoStore) ScanEnvelopes(project, generation string, after, through int64) (EnvelopeWindow, error) {
	if err := validEnvelopeRange(project, generation, after, through); err != nil {
		return EnvelopeWindow{}, err
	}
	ctx, cancel := context.WithTimeout(context.Background(), s.opTimeout)
	defer cancel()
	filter := bson.M{"project": project, "archive_metadata": bson.M{"$exists": true}, "archive_metadata.generation": generation, "archive_metadata.ordinal": bson.M{"$gt": after, "$lte": through}}
	cur, err := s.coll.Find(ctx, filter, options.Find().SetSort(bson.D{{Key: "archive_metadata.ordinal", Value: 1}}).SetHint("archive_metadata_v2_order").SetLimit(EnvelopeScanRecords+1).SetBatchSize(32).SetMaxTime(s.opTimeout))
	if err != nil {
		return EnvelopeWindow{}, err
	}
	defer cur.Close(ctx)
	w := EnvelopeWindow{}
	size := 0
	for cur.Next(ctx) {
		var d mongoDoc
		if err := cur.Decode(&d); err != nil {
			return EnvelopeWindow{}, err
		}
		e, err := d.envelope()
		if err != nil {
			return EnvelopeWindow{}, err
		}
		if e.Version != 2 || d.ID != idOf(e.Record) {
			return EnvelopeWindow{}, ErrIDConflict
		}
		raw, _ := json.Marshal(e)
		if len(w.Records) == EnvelopeScanRecords || size+len(raw) > ScanBytes {
			if len(w.Records) == 0 {
				return EnvelopeWindow{}, ErrRecordTooLarge
			}
			w.More = true
			break
		}
		size += len(raw)
		w.Records = append(w.Records, e)
	}
	return w, cur.Err()
}

// MetadataSchemaReady inspects the exact uniqueness/order contract without DDL.
func (s *MongoStore) MetadataSchemaReady() (bool, error) {
	ctx, cancel := context.WithTimeout(context.Background(), s.opTimeout)
	defer cancel()
	cursor, err := s.coll.Indexes().List(ctx)
	if err != nil {
		return false, err
	}
	defer cursor.Close(ctx)
	keys, _ := bson.Marshal(bson.D{{Key: "project", Value: 1}, {Key: "archive_metadata.generation", Value: 1}, {Key: "archive_metadata.ordinal", Value: 1}})
	partial, _ := bson.Marshal(bson.D{{Key: "archive_metadata", Value: bson.D{{Key: "$exists", Value: true}}}})
	for cursor.Next(ctx) {
		var raw bson.Raw
		if err := cursor.Decode(&raw); err != nil {
			return false, err
		}
		name, _ := raw.Lookup("name").StringValueOK()
		if name != "archive_metadata_v2_order" {
			continue
		}
		unique, _ := raw.Lookup("unique").BooleanOK()
		actualKeys, keysOK := raw.Lookup("key").DocumentOK()
		actualPartial, partialOK := raw.Lookup("partialFilterExpression").DocumentOK()
		if !unique || !keysOK || !partialOK || !bytes.Equal(keys, actualKeys) || !bytes.Equal(partial, actualPartial) {
			return false, errors.New("archive: incompatible metadata index")
		}
		return true, nil
	}
	return false, cursor.Err()
}
