package archive

import "go.mongodb.org/mongo-driver/bson"

// ReservationBytes accounts the actual serialized archive document and each
// declared index key, including the identity reference. This is an explicit
// representation budget, not a claim about DB page/journal allocation overhead.
func ReservationBytes(r Record) int64 {
	doc, _ := bson.Marshal(toDoc(r))
	id, _ := bson.Marshal(idOf(r))
	order, _ := bson.Marshal(bson.D{{Key: "project", Value: r.Project}, {Key: "session_id", Value: r.SessionID}, {Key: "seq", Value: r.Seq}})
	page, _ := bson.Marshal(bson.D{{Key: "project", Value: r.Project}, {Key: "session_id", Value: r.SessionID}, {Key: "seq", Value: r.Seq}, {Key: "source_instance", Value: r.SourceInstance}, {Key: "message_id", Value: r.MessageID}})
	return int64(len(doc) + len(id) + len(order) + len(id) + len(page) + len(id))
}

// EnvelopeReservationBytes includes the optional canonical metadata document.
// Existing declared indexes are unchanged; new indexes require their own charge.
func EnvelopeReservationBytes(e Envelope) (int64, error) {
	d, err := envelopeDoc(e)
	if err != nil {
		return 0, err
	}
	return documentReservationBytes(d), nil
}
func documentReservationBytes(d mongoDoc) int64 {
	full, _ := bson.Marshal(d)
	original, _ := bson.Marshal(toDoc(d.toRecord()))
	cost := ReservationBytes(d.toRecord()) + int64(len(full)-len(original))
	if d.Metadata != nil {
		order, _ := bson.Marshal(bson.D{{Key: "project", Value: d.Project}, {Key: "archive_metadata.generation", Value: d.Metadata.Generation}, {Key: "archive_metadata.ordinal", Value: d.Metadata.Ordinal}})
		id, _ := bson.Marshal(d.ID)
		cost += int64(len(order) + len(id))
	}
	return cost
}
