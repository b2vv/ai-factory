package archive

import (
	"context"
	"encoding/json"
	"errors"
	"go.mongodb.org/mongo-driver/bson"
	"go.mongodb.org/mongo-driver/mongo"
	"go.mongodb.org/mongo-driver/mongo/options"
)

func summaryRange(q SummaryQuery, after int64) bson.M {
	return bson.M{"archive_metadata": bson.M{"$exists": true}, "project": q.Project, "provider": q.Provider, "archive_metadata.version": 2, "archive_metadata.generation": q.Generation, "archive_metadata.ordinal": bson.M{"$gt": after, "$lte": q.Through}}
}
func originalEligibility(filter bson.M, q SummaryQuery) {
	filter["type"] = TypeMessage
	filter["archive_metadata.legacy"] = false
	filter["archive_metadata.derived_kind"] = bson.M{"$in": bson.A{"", nil}}
	filter["withdrawn"] = false
	filter["consent_epoch"] = bson.M{"$gt": q.RevokedThrough, "$lte": q.CaptureEpoch}
}

// NextSummarySession projects only session headers. The top-one keyset query uses
// the established project/generation/ordinal index; timeout is never exhaustion.
func (s *MongoStore) NextSummarySession(q SummaryQuery, after *SessionKey) (SessionKey, bool, error) {
	if !validSummaryQuery(q) || (after != nil && !validSessionKey(*after)) {
		return SessionKey{}, false, ErrSummaryQuery
	}
	ctx, cancel := context.WithTimeout(context.Background(), s.opTimeout)
	defer cancel()
	filter := summaryRange(q, q.ActivationOrdinal)
	originalEligibility(filter, q)
	if after != nil {
		filter["$or"] = bson.A{bson.M{"source_instance": bson.M{"$gt": after.SourceInstance}}, bson.M{"source_instance": after.SourceInstance, "session_id": bson.M{"$gt": after.SessionID}}}
	}
	opts := options.Find().SetProjection(bson.M{"_id": 0, "source_instance": 1, "session_id": 1}).SetSort(bson.D{{Key: "source_instance", Value: 1}, {Key: "session_id", Value: 1}}).SetLimit(1).SetBatchSize(1).SetHint("archive_metadata_v2_order").SetCollation(&options.Collation{Locale: "simple"}).SetAllowDiskUse(false).SetMaxTime(s.opTimeout)
	cursor, err := s.coll.Find(ctx, filter, opts)
	if err != nil {
		return SessionKey{}, false, err
	}
	defer cursor.Close(ctx)
	if !cursor.Next(ctx) {
		return SessionKey{}, false, cursor.Err()
	}
	var key SessionKey
	if err = cursor.Decode(&key); err != nil {
		return SessionKey{}, false, err
	}
	if !validSessionKey(key) {
		return SessionKey{}, false, ErrSummaryQuery
	}
	return key, true, nil
}

// SummaryHead intentionally has no capture/withdrawal serving filter. A malformed
// newest head must be rejected by its verifier, never replaced by an older head.
func (s *MongoStore) SummaryHead(q SummaryQuery, key SessionKey) (Envelope, bool, error) {
	if !validSummaryQuery(q) || !validSessionKey(key) {
		return Envelope{}, false, ErrSummaryQuery
	}
	ctx, cancel := context.WithTimeout(context.Background(), s.opTimeout)
	defer cancel()
	filter := summaryRange(q, q.ActivationOrdinal)
	filter["source_instance"] = key.SourceInstance
	filter["session_id"] = key.SessionID
	filter["type"] = TypeSummary
	filter["archive_metadata.derived_kind"] = DerivedSessionExtract
	var doc mongoDoc
	err := s.coll.FindOne(ctx, filter, options.FindOne().SetSort(bson.D{{Key: "archive_metadata.ordinal", Value: -1}}).SetHint("archive_metadata_v2_order").SetCollation(&options.Collation{Locale: "simple"}).SetMaxTime(s.opTimeout)).Decode(&doc)
	if errors.Is(err, mongo.ErrNoDocuments) {
		return Envelope{}, false, nil
	}
	if err != nil {
		return Envelope{}, false, err
	}
	e, err := doc.envelope()
	if err != nil {
		return Envelope{}, false, err
	}
	if doc.ID != idOf(e.Record) || !matchesSummaryRange(e, q) || e.Record.SourceInstance != key.SourceInstance || e.Record.SessionID != key.SessionID || e.Metadata.DerivedKind != DerivedSessionExtract {
		return Envelope{}, false, ErrIDConflict
	}
	return e, true, nil
}
func (s *MongoStore) ScanSummaryOriginals(q SummaryQuery, key SessionKey, after int64) (EnvelopeWindow, error) {
	if !validSummaryQuery(q) || !validSessionKey(key) || after < q.ActivationOrdinal || after > q.Through {
		return EnvelopeWindow{}, ErrSummaryQuery
	}
	ctx, cancel := context.WithTimeout(context.Background(), s.opTimeout)
	defer cancel()
	filter := summaryRange(q, after)
	filter["source_instance"] = key.SourceInstance
	filter["session_id"] = key.SessionID
	originalEligibility(filter, q)
	opts := options.Find().SetSort(bson.D{{Key: "archive_metadata.ordinal", Value: 1}}).SetHint("archive_metadata_v2_order").SetCollation(&options.Collation{Locale: "simple"}).SetLimit(EnvelopeScanRecords + 1).SetBatchSize(32).SetMaxTime(s.opTimeout)
	cursor, err := s.coll.Find(ctx, filter, opts)
	if err != nil {
		return EnvelopeWindow{}, err
	}
	defer cursor.Close(ctx)
	result := EnvelopeWindow{}
	size := 0
	for cursor.Next(ctx) {
		var doc mongoDoc
		if err = cursor.Decode(&doc); err != nil {
			return EnvelopeWindow{}, err
		}
		e, err := doc.envelope()
		if err != nil {
			return EnvelopeWindow{}, err
		}
		if doc.ID != idOf(e.Record) || !eligibleSummaryOriginal(e, q) || e.Record.SourceInstance != key.SourceInstance || e.Record.SessionID != key.SessionID || e.Metadata.Ordinal <= after {
			return EnvelopeWindow{}, ErrIDConflict
		}
		raw, err := json.Marshal(e)
		if err != nil {
			return EnvelopeWindow{}, err
		}
		if len(result.Records) == EnvelopeScanRecords || len(raw) > ScanBytes-size {
			if len(result.Records) == 0 {
				return EnvelopeWindow{}, ErrRecordTooLarge
			}
			result.More = true
			break
		}
		size += len(raw)
		result.Records = append(result.Records, e)
	}
	return result, cursor.Err()
}
