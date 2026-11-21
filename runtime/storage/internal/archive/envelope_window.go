package archive

import (
	"encoding/json"
	"errors"
	"sort"
)

const EnvelopeScanRecords = 100

type EnvelopeWindow struct {
	Records []Envelope
	More    bool
}

func validEnvelopeRange(project, generation string, after, through int64) error {
	if project == "" || generation == "" || after < 0 || through < after {
		return errors.New("archive: invalid committed metadata range")
	}
	return nil
}
func (s *MemStore) ScanEnvelopes(project, generation string, after, through int64) (EnvelopeWindow, error) {
	if err := validEnvelopeRange(project, generation, after, through); err != nil {
		return EnvelopeWindow{}, err
	}
	if !s.up {
		return EnvelopeWindow{}, ErrUnavailable
	}
	var list []Envelope
	for _, r := range s.recs[project] {
		e, found, err := s.LookupEnvelope(r)
		if err != nil {
			return EnvelopeWindow{}, err
		}
		if found && e.Version == 2 && e.Metadata.Generation == generation && e.Metadata.Ordinal > after && e.Metadata.Ordinal <= through {
			list = append(list, e)
		}
	}
	sort.Slice(list, func(i, j int) bool { return list[i].Metadata.Ordinal < list[j].Metadata.Ordinal })
	w := EnvelopeWindow{}
	size := 0
	for _, e := range list {
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
	return w, nil
}
