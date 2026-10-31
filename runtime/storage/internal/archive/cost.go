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
