// MongoStore is the production archive backend: a real MongoDB-backed implementation of
// the Store interface. It is used only when Mongo is explicitly enabled; the hermetic
// suite keeps using MemStore. It never depends on PostgreSQL (archive queries are served
// from the archive itself).
//
// Identity/idempotency: each record is identified by a COMPOUND _id document
// {project, session_id, message_id}. A compound document _id is compared structurally, so
// distinct field tuples can never collide the way a delimiter-joined string key can
// (e.g. ("a|b","c") vs ("a","b|c")). A replayed delivery with the SAME identity AND the
// same content is a no-op (idempotent); the SAME identity with a DIFFERENT payload is NOT
// silently dropped - it returns ErrIDConflict so a collision/tamper/edit is surfaced to the
// caller rather than hidden. Availability is a cached flag refreshed by Ping, so health
// reports the real backend state and never a fabricated healthy.
package archive

import (
	"context"
	"errors"
	"sync/atomic"
	"time"

	"go.mongodb.org/mongo-driver/bson"
	"go.mongodb.org/mongo-driver/mongo"
	"go.mongodb.org/mongo-driver/mongo/options"
	"go.mongodb.org/mongo-driver/mongo/readconcern"
	"go.mongodb.org/mongo-driver/mongo/writeconcern"
)

// docID is the compound, unambiguous identity of an archived record. Per PLAN §4/D7 the
// provider session/message IDs are namespaced by source instance + session, so the source
// instance is part of the identity (two instances replaying the "same" provider IDs do not
// collide). A compound document _id is compared structurally (no delimiter ambiguity).
type docID struct {
	Project        string `bson:"p"`
	SourceInstance string `bson:"si"`
	SessionID      string `bson:"s"`
	MessageID      string `bson:"m"`
}

// mongoDoc is the BSON projection of Record. Identity lives in the compound _id; the
// top-level fields are retained for querying/ordering.
type mongoDoc struct {
	ID             docID        `bson:"_id"`
	Project        string       `bson:"project"`
	Provider       string       `bson:"provider"`
	SourceInstance string       `bson:"source_instance"`
	SessionID      string       `bson:"session_id"`
	MessageID      string       `bson:"message_id"`
	Seq            int          `bson:"seq"`
	ParentID       string       `bson:"parent_id"`
	Type           RecordType   `bson:"type"`
	Role           string       `bson:"role"`
	Text           string       `bson:"text"`
	Edited         bool         `bson:"edited"`
	Withdrawn      bool         `bson:"withdrawn"`
	ConsentEpoch   int64        `bson:"consent_epoch"`
	Metadata       *metadataDoc `bson:"archive_metadata,omitempty"`
}

func idOf(r Record) docID {
	return docID{Project: r.Project, SourceInstance: r.SourceInstance, SessionID: r.SessionID, MessageID: r.MessageID}
}

func toDoc(r Record) mongoDoc {
	return mongoDoc{
		ID: idOf(r), Project: r.Project, Provider: r.Provider, SourceInstance: r.SourceInstance,
		SessionID: r.SessionID, MessageID: r.MessageID, Seq: r.Seq, ParentID: r.ParentID,
		Type: r.Type, Role: r.Role, Text: r.Text, Edited: r.Edited, Withdrawn: r.Withdrawn,
		ConsentEpoch: r.ConsentEpoch,
	}
}

func (d mongoDoc) toRecord() Record {
	return Record{
		Project: d.Project, Provider: d.Provider, SourceInstance: d.SourceInstance,
		SessionID: d.SessionID, MessageID: d.MessageID, Seq: d.Seq, ParentID: d.ParentID,
		Type: d.Type, Role: d.Role, Text: d.Text, Edited: d.Edited, Withdrawn: d.Withdrawn,
		ConsentEpoch: d.ConsentEpoch,
	}
}

// sameContent reports whether two records are identical in everything except identity
// (identity is the _id). Used to distinguish a benign replay from a conflicting payload.
func sameContent(a, b Record) bool {
	a.Project, a.SourceInstance, a.SessionID, a.MessageID = "", "", "", ""
	b.Project, b.SourceInstance, b.SessionID, b.MessageID = "", "", "", ""
	return a == b
}

// ErrIDConflict is returned when a record with an existing identity arrives carrying a
// different payload (not a benign replay). It is never silently dropped.
var ErrIDConflict = errors.New("archive: record identity already stored with a different payload (conflict, not a replay)")

// ErrUnavailable is the shared fail-closed signal when an enabled backend is down.
var ErrUnavailable = errors.New("archive: backend unavailable; serving fails closed (no fabricated empty history)")

// MongoStore implements Store against a real MongoDB deployment.
type MongoStore struct {
	client    *mongo.Client
	coll      *mongo.Collection
	up        atomic.Bool
	opTimeout time.Duration
}

// OpenMongo connects, verifies the connection, and ensures the query index. It returns an
// error if the backend cannot be reached or the index cannot be created, so an
// enabled-but-broken backend never starts as if healthy.
func OpenMongo(ctx context.Context, uri, db, collection string) (*MongoStore, error) {
	return openMongo(ctx, uri, db, collection, true)
}

// OpenMongoForBudget verifies connectivity without creating collections or indexes.
// The caller must admit startup metadata before opening the writing adapter.
func OpenMongoForBudget(ctx context.Context, uri, db, collection string) (*MongoStore, error) {
	return openMongo(ctx, uri, db, collection, false)
}
func openMongo(ctx context.Context, uri, db, collection string, ensureIndexes bool) (*MongoStore, error) {
	// "Durable archive commit" is bounded EXACTLY by this write concern: a Put returns
	// success only after the write is acknowledged by a MAJORITY of the deployment AND
	// journaled to disk (Journal is set explicitly to true rather than left to the server
	// default, so the durability claim is unambiguous). Reads use majority read concern.
	// NOTE ON TOPOLOGY: on a SINGLE-NODE standalone (the test deployment) "majority" == w:1,
	// so what is proven there is single-node journaled durability; a true multi-node majority
	// guarantee requires a replica set and is NOT exercised by the single-node tests.
	journal := true
	clientOpts := options.Client().ApplyURI(uri).
		SetWriteConcern(&writeconcern.WriteConcern{W: "majority", Journal: &journal}).
		SetReadConcern(readconcern.Majority())
	client, err := mongo.Connect(ctx, clientOpts)
	if err != nil {
		return nil, err
	}
	s := &MongoStore{client: client, coll: client.Database(db).Collection(collection), opTimeout: 5 * time.Second}
	if err := s.Ping(ctx); err != nil {
		_ = client.Disconnect(context.Background())
		return nil, err
	}
	// Identity uniqueness is inherent in the compound _id. Add a query index for All()'s
	// project-scoped, session/seq-ordered scan.
	if !ensureIndexes {
		return s, nil
	}
	ixCtx, cancel := context.WithTimeout(ctx, s.opTimeout)
	defer cancel()
	if _, err := s.coll.Indexes().CreateOne(ixCtx, mongo.IndexModel{
		Keys: bson.D{{Key: "project", Value: 1}, {Key: "session_id", Value: 1}, {Key: "seq", Value: 1}},
	}); err != nil {
		_ = client.Disconnect(context.Background())
		return nil, err
	}

	if _, err := s.coll.Indexes().CreateOne(ixCtx, mongo.IndexModel{Keys: bson.D{{Key: "project", Value: 1}, {Key: "session_id", Value: 1}, {Key: "seq", Value: 1}, {Key: "source_instance", Value: 1}, {Key: "message_id", Value: 1}}, Options: options.Index().SetName("archive_page_v1")}); err != nil {
		_ = client.Disconnect(context.Background())
		return nil, err
	}
	return s, nil
}

// Ping refreshes and returns the real backend availability.
func (s *MongoStore) Ping(ctx context.Context) error {
	pctx, cancel := context.WithTimeout(ctx, s.opTimeout)
	defer cancel()
	err := s.client.Ping(pctx, nil)
	s.up.Store(err == nil)
	return err
}

// Available reports the last observed backend state (refreshed by Ping). It never
// fabricates healthy.
func (s *MongoStore) Available() bool { return s.up.Load() }

// Put durably writes one record. A repeated identity with identical content is an
// idempotent no-op; a repeated identity with a DIFFERENT payload returns ErrIDConflict
// (never silently dropped). Any other backend error is returned and marks the store
// unavailable.
func (s *MongoStore) Put(r Record) error {
	ctx, cancel := context.WithTimeout(context.Background(), s.opTimeout)
	defer cancel()
	_, err := s.coll.InsertOne(ctx, toDoc(r))
	if err == nil {
		s.up.Store(true)
		return nil
	}
	if mongo.IsDuplicateKeyError(err) {
		// Identity already present: compare content to tell a replay from a conflict.
		var existing mongoDoc
		fctx, fcancel := context.WithTimeout(context.Background(), s.opTimeout)
		defer fcancel()
		if ferr := s.coll.FindOne(fctx, bson.M{"_id": idOf(r)}).Decode(&existing); ferr != nil {
			s.up.Store(false)
			return ferr
		}
		s.up.Store(true)
		if sameContent(existing.toRecord(), r) {
			return nil // benign idempotent replay
		}
		return ErrIDConflict
	}
	s.up.Store(false)
	return err
}

// Fetch returns every stored record for a project in session/seq order. A query/cursor/decode
// error is PROPAGATED (and marks the store unavailable); it is NEVER turned into a silent empty
// result, so a read failure can never be served as "no history". Callers must surface the
// error (e.g. HTTP 503), not a 200 with empty hits.
func (s *MongoStore) Fetch(project string) ([]Record, error) {
	ctx, cancel := context.WithTimeout(context.Background(), s.opTimeout)
	defer cancel()
	// Sort on the FULL identity (P2-1), not just session+seq: records from different source
	// instances can share session+seq, so a unique tie-breaker is required for a stable total
	// order across requests (otherwise offset pagination can duplicate/skip records). The local
	// archive.Query sort uses the same key order.
	cur, err := s.coll.Find(ctx, bson.M{"project": project},
		options.Find().SetSort(bson.D{{Key: "session_id", Value: 1}, {Key: "seq", Value: 1}, {Key: "source_instance", Value: 1}, {Key: "message_id", Value: 1}}))
	if err != nil {
		s.up.Store(false)
		return nil, err
	}
	defer cur.Close(ctx)
	var out []Record
	for cur.Next(ctx) {
		var d mongoDoc
		if err := cur.Decode(&d); err != nil {
			s.up.Store(false)
			return nil, err
		}
		out = append(out, d.toRecord())
	}
	if err := cur.Err(); err != nil {
		s.up.Store(false)
		return nil, err
	}
	s.up.Store(true)
	return out, nil
}

// StorageBytes returns the archive database's on-disk footprint toward the D4 live-data cap:
// dbStats.storageSize PLUS indexSize (indexes count against the agreed total, not just the
// collection storage). An error is returned (never a silent 0) so the caller can fail closed.
func (s *MongoStore) StorageBytes(ctx context.Context) (int64, error) {
	cctx, cancel := context.WithTimeout(ctx, s.opTimeout)
	defer cancel()
	var res struct {
		StorageSize int64 `bson:"storageSize"`
		IndexSize   int64 `bson:"indexSize"`
	}
	if err := s.coll.Database().RunCommand(cctx, bson.D{{Key: "dbStats", Value: 1}}).Decode(&res); err != nil {
		return 0, err
	}
	return res.StorageSize + res.IndexSize, nil
}

// Purge physically deletes a project's records (or one session's) from the archive
// collection (DeleteMany). It is real erasure, not a serve-side hide. An error is returned
// (never silently 0) and marks the backend unavailable.
func (s *MongoStore) Purge(project, session string) (int, error) {
	ctx, cancel := context.WithTimeout(context.Background(), s.opTimeout)
	defer cancel()
	filter := bson.M{"project": project}
	if session != "" {
		filter["session_id"] = session
	}
	res, err := s.coll.DeleteMany(ctx, filter)
	if err != nil {
		s.up.Store(false)
		return 0, err
	}
	s.up.Store(true)
	return int(res.DeletedCount), nil
}

// Close disconnects the client.
func (s *MongoStore) Close() error {
	ctx, cancel := context.WithTimeout(context.Background(), s.opTimeout)
	defer cancel()
	return s.client.Disconnect(ctx)
}
