package archive

import "encoding/json"

// MetadataStore adds atomic source metadata projection. It is inactive until the
// control migration witness, budget protocol and all intake readers are enabled.
type MetadataStore interface {
	PutEnvelope(Envelope) error
	AttachMetadata(Envelope) error
	LookupEnvelope(Record) (Envelope, bool, error)
}

func (s *MemStore) PutEnvelope(e Envelope) error {
	if !s.up {
		return ErrUnavailable
	}
	canonical, err := canonicalEnvelope(e)
	if err != nil {
		return err
	}
	existing, found, err := s.LookupEnvelope(e.Record)
	if err != nil {
		return err
	}
	if found {
		if equalEnvelope(existing, canonical) {
			return nil
		}
		return ErrIDConflict
	}
	if err := s.uniqueMetadataOrdinal(canonical); err != nil {
		return err
	}
	if err := s.Put(e.Record); err != nil {
		return err
	}
	if s.metadata == nil {
		s.metadata = map[string]Metadata{}
	}
	s.metadata[IdentityKey(e.Record)] = canonical.Metadata
	return nil
}
func equalEnvelope(a, b Envelope) bool {
	aa, ea := EncodeEnvelope(a)
	bb, eb := EncodeEnvelope(b)
	return ea == nil && eb == nil && string(aa) == string(bb)
}
func (s *MemStore) AttachMetadata(e Envelope) error {
	if !s.up {
		return ErrUnavailable
	}
	e, err := canonicalEnvelope(e)
	if err != nil {
		return err
	}
	if !e.Metadata.Legacy {
		return ErrIDConflict
	}
	old, found, err := s.LookupEnvelope(e.Record)
	if err != nil {
		return err
	}
	if !found || old.Record != e.Record {
		return ErrIDConflict
	}
	if old.Version == 2 {
		if equalEnvelope(old, e) {
			return nil
		}
		return ErrIDConflict
	}
	if err := s.uniqueMetadataOrdinal(e); err != nil {
		return err
	}
	if s.metadata == nil {
		s.metadata = map[string]Metadata{}
	}
	s.metadata[IdentityKey(e.Record)] = e.Metadata
	return nil
}
func (s *MemStore) LookupEnvelope(r Record) (Envelope, bool, error) {
	got, found, err := s.Lookup(r)
	if err != nil || !found {
		return Envelope{}, found, err
	}
	m, ok := s.metadata[IdentityKey(got)]
	if !ok {
		return Envelope{Version: 1, Record: got, Metadata: Metadata{Legacy: true}}, true, nil
	}
	// Return detached metadata; callers cannot mutate stored timestamp pointers.
	raw, _ := json.Marshal(Envelope{Version: 2, Record: got, Metadata: m})
	e, err := DecodeEnvelope(2, raw)
	return e, true, err
}

func (s *MemStore) uniqueMetadataOrdinal(e Envelope) error {
	for _, r := range s.recs[e.Record.Project] {
		m, ok := s.metadata[IdentityKey(r)]
		if ok && m.Generation == e.Metadata.Generation && m.Ordinal == e.Metadata.Ordinal && IdentityKey(r) != IdentityKey(e.Record) {
			return ErrIDConflict
		}
	}
	return nil
}
