package archive

import (
	"bytes"
	"encoding/json"
	"errors"
	"io"
	"time"
)

type Metadata struct {
	Generation      string     `json:"generation"`
	Ordinal         int64      `json:"ordinal"`
	CapturedAt      *time.Time `json:"captured_at"`
	SourceEventTime *time.Time `json:"source_event_time"`
	Legacy          bool       `json:"legacy"`
}

type Envelope struct {
	Version  int      `json:"version"`
	Record   Record   `json:"record"`
	Metadata Metadata `json:"metadata"`
}

func EncodeEnvelope(e Envelope) ([]byte, error) {
	e, err := canonicalEnvelope(e)
	if err != nil {
		return nil, err
	}
	return json.Marshal(e)
}
func DecodeEnvelope(format uint8, payload []byte) (Envelope, error) {
	switch format {
	case 1:
		var r Record
		if err := json.Unmarshal(payload, &r); err != nil {
			return Envelope{}, err
		}
		return Envelope{Version: 1, Record: r, Metadata: Metadata{Legacy: true}}, nil
	case 2:
		var e Envelope
		d := json.NewDecoder(bytes.NewReader(payload))
		d.DisallowUnknownFields()
		if err := d.Decode(&e); err != nil {
			return Envelope{}, err
		}
		if err := d.Decode(new(any)); err != io.EOF {
			return Envelope{}, errors.New("archive: trailing envelope data")
		}
		return canonicalEnvelope(e)
	default:
		return Envelope{}, errors.New("archive: unsupported envelope format")
	}
}

// Metadata is outside Record so neither identity nor historical content hashes change.
// Legacy migration assigns ordering only; it cannot establish historical times.
func canonicalEnvelope(e Envelope) (Envelope, error) {
	m := e.Metadata
	if e.Version != 2 || m.Generation == "" || len(m.Generation) > 128 || m.Ordinal <= 0 {
		return Envelope{}, errors.New("archive: invalid metadata version/order")
	}
	if m.Legacy {
		if m.CapturedAt != nil || m.SourceEventTime != nil {
			return Envelope{}, errors.New("archive: legacy times must be unknown")
		}
	} else if m.CapturedAt == nil {
		return Envelope{}, errors.New("archive: capture time required")
	}
	for _, p := range []**time.Time{&m.CapturedAt, &m.SourceEventTime} {
		if *p != nil {
			if (*p).IsZero() {
				return Envelope{}, errors.New("archive: zero time is not evidence")
			}
			v := (*p).UTC()
			if _, err := v.MarshalJSON(); err != nil {
				return Envelope{}, err
			}
			*p = &v
		}
	}
	e.Metadata = m
	return e, nil
}

// IndexCheckpoint binds derived progress to authoritative source and policy.
// It is transport data shared by control receipts and the derived index.
type IndexCheckpoint struct {
	Project, SourceGeneration, ProjectionGeneration, PolicyRevision string
	Ordinal                                                         int64
	Complete                                                        bool
}
